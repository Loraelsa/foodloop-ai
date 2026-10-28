import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, metrics
from .geo import bbox, within
from .ratelimit import limit_api, limit_auth
from .config import CO2E_PER_KG_FOOD, KG_PER_MEAL
from .db import get_db
from .ml import engine
from .ml.features import CATEGORIES, STORAGES
from .models import Listing, Notification, Pickup, Review, User
from .routing import haversine_km, plan_route
from .security import current_user, hash_password, make_token, require_role, verify_password

router = APIRouter(prefix="/api", dependencies=[Depends(limit_api)])
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L: easy to read out loud


def new_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))

Category = Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]
Storage = Literal[tuple(STORAGES)]  # type: ignore[valid-type]


# ---------------- schemas ----------------
class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=100)
    role: Literal["vendor", "citizen", "ngo"]
    lat: float = Field(28.6139, ge=-90, le=90)
    lon: float = Field(77.2090, ge=-180, le=180)


class LoginIn(BaseModel):
    email: str
    password: str


class ListingIn(BaseModel):
    item_name: str = Field(min_length=2, max_length=120)
    category: Category
    quantity_kg: float = Field(gt=0, le=500)
    mrp: float = Field(0, ge=0, le=100000)
    hours_since_prepared: float = Field(ge=0, le=500)
    storage: Storage
    ambient_temp_c: float = Field(28, ge=-10, le=55)


class AcceptIn(BaseModel):
    listing_ids: list[int] = Field(min_length=1, max_length=30)
    vehicles: int = Field(1, ge=1, le=5)
    capacity_kg: float | None = Field(None, gt=0)


def user_out(u: User):
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "lat": u.lat, "lon": u.lon,
            "verified": u.verified}


def listing_out(l: Listing, viewer: User | None = None):
    d = {
        "id": l.id, "item_name": l.item_name, "category": l.category, "quantity_kg": l.quantity_kg,
        "mrp": l.mrp, "storage": l.storage, "hours_since_prepared": l.hours_since_prepared,
        "remaining_hours": l.remaining_hours, "freshness_score": l.freshness_score,
        "decision": l.decision, "discount_pct": l.discount_pct, "price": l.price, "status": l.status,
        "vendor": l.vendor.name if l.vendor else None, "vendor_id": l.vendor_id, "lat": l.lat, "lon": l.lon,
        "created_at": l.created_at.isoformat() if l.created_at else None, "has_photo": l.has_photo,
    }
    if viewer is not None:
        d["distance_km"] = round(haversine_km(viewer.lat, viewer.lon, l.lat, l.lon), 2)
    return d


# ---------------- auth ----------------
@router.post("/auth/register", status_code=201, dependencies=[Depends(limit_auth)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "That email is already registered - log in instead")
    u = User(name=body.name.strip(), email=email, password_hash=hash_password(body.password),
             role=body.role, lat=body.lat, lon=body.lon,
             verified=(body.role == "citizen"))   # vendors and NGOs wait for admin approval
    db.add(u)
    db.commit()
    return {"token": make_token(u), "user": user_out(u)}


@router.post("/auth/login", dependencies=[Depends(limit_auth)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": make_token(u), "user": user_out(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


# ---------------- trust & safety helpers ----------------
def require_verified(user: User):
    if not user.verified:
        raise HTTPException(403, "Your account is waiting for admin approval. You can use the freshness check meanwhile.")


def notify_nearby_ngos(db: Session, l: Listing, vendor: User):
    """In-app alert to every verified NGO within NOTIFY_RADIUS_KM of a new donation."""
    lat0, lat1, lon0, lon1 = bbox(l.lat, l.lon, config.NOTIFY_RADIUS_KM)
    ngos = db.scalars(select(User).where(User.role == "ngo", User.verified.is_(True),
                                         User.lat.between(lat0, lat1), User.lon.between(lon0, lon1))).all()
    for n in within(ngos, l.lat, l.lon, config.NOTIFY_RADIUS_KM):
        db.add(Notification(user_id=n.id, kind="donation", listing_id=l.id,
                            message=f"New donation: {l.quantity_kg:g} kg {l.item_name} from {vendor.name} "
                                    f"({haversine_km(n.lat, n.lon, l.lat, l.lon):.1f} km away, about {l.remaining_hours:.1f} h left)"))


# ---------------- vendor ----------------
@router.post("/predict")
def predict(body: ListingIn, user: User = Depends(require_role("vendor"))):
    """Preview the ML decision without saving anything."""
    return engine.assess(body.category, body.storage, body.hours_since_prepared,
                         body.ambient_temp_c, body.quantity_kg, body.mrp)


@router.post("/listings", status_code=201)
def create_listing(body: ListingIn, user: User = Depends(require_role("vendor")), db: Session = Depends(get_db)):
    require_verified(user)
    a = engine.assess(body.category, body.storage, body.hours_since_prepared,
                      body.ambient_temp_c, body.quantity_kg, body.mrp)
    a.pop("safety_margin_h", None)
    l = Listing(vendor_id=user.id, item_name=body.item_name.strip(), category=body.category,
                quantity_kg=body.quantity_kg, mrp=body.mrp, hours_since_prepared=body.hours_since_prepared,
                storage=body.storage, ambient_temp_c=body.ambient_temp_c, lat=user.lat, lon=user.lon,
                pickup_code=new_code(), **a)
    db.add(l)
    db.flush()
    if l.decision == "donate":
        notify_nearby_ngos(db, l, user)
    db.commit()
    metrics.invalidate()
    return listing_out(l)


@router.get("/listings/mine")
def my_listings(user: User = Depends(require_role("vendor")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Listing).where(Listing.vendor_id == user.id).order_by(Listing.id.desc()).limit(100))
    return [listing_out(l) for l in rows]


@router.post("/listings/{listing_id}/complete")
def complete_listing(listing_id: int, user: User = Depends(require_role("vendor")), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or l.vendor_id != user.id:
        raise HTTPException(404, "Listing not found")
    if l.decision == "donate":
        raise HTTPException(400, "Donations are completed by the NGO when the pickup is done")
    if l.decision == "sell" and l.status != "reserved":
        raise HTTPException(400, "Nobody has reserved this item yet")
    l.status = "completed"
    db.commit()
    metrics.invalidate()
    return listing_out(l)


# ---------------- citizen ----------------
@router.get("/market")
def market(radius_km: float = Query(30, gt=0, le=500), user: User = Depends(require_role("citizen")),
           db: Session = Depends(get_db)):
    lat0, lat1, lon0, lon1 = bbox(user.lat, user.lon, radius_km)   # indexed pre-filter, then exact distance
    rows = db.scalars(select(Listing).where(Listing.decision == "sell", Listing.status == "available",
                                            Listing.lat.between(lat0, lat1), Listing.lon.between(lon0, lon1))
                      .order_by(Listing.id.desc()).limit(300)).all()
    out = [listing_out(l, user) for l in within(rows, user.lat, user.lon, radius_km)]
    ratings = vendor_ratings(db, {d["vendor_id"] for d in out})
    for d in out:
        d["vendor_rating"], d["vendor_reviews"] = ratings.get(d["vendor_id"], (None, 0))
    return sorted(out, key=lambda d: d["distance_km"])


def vendor_ratings(db: Session, vendor_ids) -> dict:
    """{vendor_id: (average stars, number of reviews)} in one grouped query."""
    if not vendor_ids:
        return {}
    rows = db.execute(select(Review.vendor_id, func.avg(Review.stars), func.count(Review.id))
                      .where(Review.vendor_id.in_(vendor_ids)).group_by(Review.vendor_id)).all()
    return {v: (round(float(avg), 1), n) for v, avg, n in rows}


@router.post("/listings/{listing_id}/cancel")
def cancel_reservation(listing_id: int, user: User = Depends(require_role("citizen")), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or l.reserved_by != user.id or l.status != "reserved":
        raise HTTPException(409, "Only your own reserved orders can be cancelled")
    l.status, l.reserved_by, l.pickup_code = "available", None, new_code()   # fresh code so the old QR stops working
    db.commit()
    metrics.invalidate()
    return {"ok": True}


@router.post("/listings/{listing_id}/reserve")
def reserve(listing_id: int, user: User = Depends(require_role("citizen")), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or l.decision != "sell" or l.status != "available":
        raise HTTPException(409, "This item is no longer available")
    l.status, l.reserved_by = "reserved", user.id
    db.commit()
    metrics.invalidate()
    return listing_out(l, user)


# ---------------- NGO ----------------
@router.get("/donations")
def donations(radius_km: float = Query(50, gt=0, le=500), user: User = Depends(require_role("ngo")),
              db: Session = Depends(get_db)):
    lat0, lat1, lon0, lon1 = bbox(user.lat, user.lon, radius_km)
    rows = db.scalars(select(Listing).where(Listing.decision == "donate", Listing.status == "available",
                                            Listing.lat.between(lat0, lat1), Listing.lon.between(lon0, lon1))
                      .order_by(Listing.id.desc()).limit(300)).all()
    out = [listing_out(l, user) for l in within(rows, user.lat, user.lon, radius_km)]
    ratings = vendor_ratings(db, {d["vendor_id"] for d in out})
    for d in out:
        d["vendor_rating"], d["vendor_reviews"] = ratings.get(d["vendor_id"], (None, 0))
    return sorted(out, key=lambda d: d["distance_km"])


def vendor_ratings(db: Session, vendor_ids) -> dict:
    """{vendor_id: (average stars, number of reviews)} in one grouped query."""
    if not vendor_ids:
        return {}
    rows = db.execute(select(Review.vendor_id, func.avg(Review.stars), func.count(Review.id))
                      .where(Review.vendor_id.in_(vendor_ids)).group_by(Review.vendor_id)).all()
    return {v: (round(float(avg), 1), n) for v, avg, n in rows}


@router.post("/listings/{listing_id}/cancel")
def cancel_reservation(listing_id: int, user: User = Depends(require_role("citizen")), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or l.reserved_by != user.id or l.status != "reserved":
        raise HTTPException(409, "Only your own reserved orders can be cancelled")
    l.status, l.reserved_by, l.pickup_code = "available", None, new_code()   # fresh code so the old QR stops working
    db.commit()
    metrics.invalidate()
    return {"ok": True}


@router.post("/ngo/accept", status_code=201)
def accept(body: AcceptIn, user: User = Depends(require_role("ngo")), db: Session = Depends(get_db)):
    require_verified(user)
    rows = db.scalars(select(Listing).where(Listing.id.in_(body.listing_ids))).all()
    if len(rows) != len(set(body.listing_ids)):
        raise HTTPException(404, "One or more listings do not exist")
    bad = [l.id for l in rows if l.decision != "donate" or l.status != "available"]
    if bad:
        raise HTTPException(409, f"Listings no longer available: {bad}")
    order = {i: k for k, i in enumerate(body.listing_ids)}  # acceptance order = baseline
    rows.sort(key=lambda l: order[l.id])
    stops = [{"id": l.id, "lat": l.lat, "lon": l.lon, "kg": l.quantity_kg,
              "name": f"{l.vendor.name} - {l.item_name}"} for l in rows]
    plan = plan_route((user.lat, user.lon), stops, body.vehicles, body.capacity_kg)
    if not plan.get("feasible", True):
        raise HTTPException(422, "Selected items exceed vehicle capacity - add vehicles or remove items")
    p = Pickup(ngo_id=user.id, route=plan, total_kg=sum(l.quantity_kg for l in rows),
               distance_km=plan["distance_km"], baseline_km=plan["baseline_km"], co2_saved_kg=plan["co2_saved_kg"])
    db.add(p)
    db.flush()
    for l in rows:
        l.status, l.pickup_id = "accepted", p.id
    db.commit()
    metrics.invalidate()
    return pickup_out(p)


def pickup_out(p: Pickup):
    return {"id": p.id, "status": p.status, "total_kg": p.total_kg, "distance_km": p.distance_km,
            "baseline_km": p.baseline_km, "co2_saved_kg": p.co2_saved_kg, "route": p.route,
            "created_at": p.created_at.isoformat() if p.created_at else None}


@router.get("/ngo/pickups")
def pickups(user: User = Depends(require_role("ngo")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Pickup).where(Pickup.ngo_id == user.id).order_by(Pickup.id.desc()).limit(50))
    return [pickup_out(p) for p in rows]


@router.post("/ngo/pickups/{pickup_id}/complete")
def complete_pickup(pickup_id: int, user: User = Depends(require_role("ngo")), db: Session = Depends(get_db)):
    p = db.get(Pickup, pickup_id)
    if not p or p.ngo_id != user.id:
        raise HTTPException(404, "Pickup not found")
    if p.status == "completed":
        return pickup_out(p)
    p.status = "completed"
    for l in db.scalars(select(Listing).where(Listing.pickup_id == p.id)):
        l.status = "completed"
    db.commit()
    metrics.invalidate()
    return pickup_out(p)


# ---------------- impact + system ----------------
def _compute_impact(db: Session):
    def kg(*conds):
        return float(db.scalar(select(func.coalesce(func.sum(Listing.quantity_kg), 0.0)).where(*conds)) or 0.0)

    sold = kg(Listing.status == "completed", Listing.decision == "sell")
    donated = kg(Listing.status == "completed", Listing.decision == "donate")
    composted = kg(Listing.status == "completed", Listing.decision == "compost")
    saved = sold + donated
    route_co2 = float(db.scalar(select(func.coalesce(func.sum(Pickup.co2_saved_kg), 0.0))
                                .where(Pickup.status == "completed")) or 0.0)
    return {
        "kg_saved": round(saved, 2), "kg_sold": round(sold, 2), "kg_donated": round(donated, 2),
        "kg_composted": round(composted, 2), "meals_redistributed": int(donated / KG_PER_MEAL),
        "co2_avoided_food_kg": round(saved * CO2E_PER_KG_FOOD, 2), "co2_avoided_routes_kg": round(route_co2, 3),
        "listings_total": int(db.scalar(select(func.count(Listing.id))) or 0),
        "pickups_completed": int(db.scalar(select(func.count(Pickup.id)).where(Pickup.status == "completed")) or 0),
        "assumptions": {"co2e_per_kg_food": CO2E_PER_KG_FOOD, "kg_per_meal": KG_PER_MEAL},
    }


@router.get("/impact")
def impact(db: Session = Depends(get_db)):
    return metrics.cached("impact", lambda: _compute_impact(db))


@router.get("/system/metrics")
def system_metrics():
    return metrics.summary()


@router.get("/health")
def health():
    return {"status": "ok"}


from .api_extra import extra  # noqa: E402  (registered after the core routes so shared helpers exist)
router.include_router(extra)
from .api_help import help_router  # noqa: E402
router.include_router(help_router)
