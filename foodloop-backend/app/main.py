"""FoodLoop AI backend (FastAPI)."""
import datetime as dt, os, random, time
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import db, ml, shelf, routing, impact as imp

SECRET = os.environ.get("FOODLOOP_SECRET", "dev-only-secret-set-FOODLOOP_SECRET-in-production")
ALGO = "HS256"
USERS = {"vendor@demo": ("vendor", 1), "ngo@demo": ("ngo", 1), "customer@demo": ("customer", 0), "admin@demo": ("admin", 0)}

app = FastAPI(title="FoodLoop AI", version="1.0")
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
STATE = {}
CACHE = {}            # key -> (expires_at, value)
CACHE_TTL = 30.0
STATS = {"hits": 0, "miss": 0}


@app.on_event("startup")
def _startup():
    db.init()
    STATE["shelf"] = ml.load_shelf()
    STATE["surplus"] = ml.load_surplus()


def cached(key, fn, enabled=True):
    now = time.time()
    if enabled and key in CACHE and CACHE[key][0] > now:
        STATS["hits"] += 1
        return CACHE[key][1]
    STATS["miss"] += 1
    v = fn()
    if enabled:
        CACHE[key] = (now + CACHE_TTL, v)
    return v


def invalidate():
    CACHE.clear()


def session():
    s = db.SessionLocal()
    try:
        yield s
    finally:
        s.close()


def auth(*roles):
    def dep(authorization: str = Header(default="")):
        try:
            tok = jwt.decode(authorization.replace("Bearer ", ""), SECRET, algorithms=[ALGO])
        except Exception:
            raise HTTPException(401, "Invalid or missing token")
        if roles and tok["role"] not in roles:
            raise HTTPException(403, "Role not permitted")
        return tok
    return dep


class Login(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def login(b: Login):
    if b.email not in USERS or b.password != "demo-password":
        raise HTTPException(401, "Wrong email or password")
    role, ent = USERS[b.email]
    exp = dt.datetime.utcnow() + dt.timedelta(hours=8)
    return {"token": jwt.encode({"sub": b.email, "role": role, "entity": ent, "exp": exp}, SECRET, ALGO), "role": role}


class ListingIn(BaseModel):
    vendor_id: int = 1
    item: str = Field(min_length=1, max_length=80)
    category: str
    storage: str
    temp: float = Field(ge=5, le=50)
    hours: float = Field(ge=0, le=500)
    qty: float = Field(gt=0)
    unit: str = "portions"
    kg_per_unit: float = Field(gt=0)
    mrp: float = Field(ge=0)


def decision_for(b):
    if b.category not in shelf.CATEGORIES or b.storage not in shelf.STORAGES:
        raise HTTPException(422, "Unknown category or storage")
    kg = b.qty * b.kg_per_unit
    rem = ml.predict_remaining(STATE["shelf"], b.category, b.storage, b.temp, b.hours, kg)
    d = shelf.decide_from_hours(rem)
    disc = shelf.discount_pct(rem) if d == "sell" else 0
    return rem, d, disc


@app.post("/listings")
def create_listing(b: ListingIn, s=Depends(session), tok=Depends(auth("vendor", "admin"))):
    rem, d, disc = decision_for(b)
    now = dt.datetime.utcnow()
    row = db.Listing(vendor_id=b.vendor_id, item=b.item, category=b.category, storage=b.storage, temp=b.temp,
                     hours=b.hours, qty=b.qty, unit=b.unit, kg_per_unit=b.kg_per_unit, mrp=b.mrp,
                     remaining=round(rem, 2), decision=d, discount=disc, price=round(b.mrp * (1 - disc / 100), 2),
                     expires=now + dt.timedelta(hours=max(rem, 0)))
    s.add(row); s.commit(); invalidate()
    return {"id": row.id, "remaining_h": row.remaining, "decision": d, "discount": disc, "price": row.price}


def _ser(l):
    return {"id": l.id, "vendor_id": l.vendor_id, "item": l.item, "category": l.category, "qty": l.qty, "unit": l.unit,
            "kg": round(l.qty * l.kg_per_unit, 2), "decision": l.decision, "discount": l.discount, "price": l.price,
            "remaining_h": l.remaining, "status": l.status}


@app.get("/listings")
def listings(decision: str = "sell", limit: int = 200, s=Depends(session)):
    q = s.query(db.Listing).filter(db.Listing.status == "live", db.Listing.decision == decision).order_by(db.Listing.expires).limit(limit)
    return [_ser(l) for l in q]


class PlanIn(BaseModel):
    ngo_id: int = 1
    listing_ids: list[int]
    time_limit_ms: int = 200


@app.post("/pickups/plan")
def plan(b: PlanIn, s=Depends(session), tok=Depends(auth("ngo", "admin"))):
    ngo = s.get(db.Ngo, b.ngo_id)
    ls = s.query(db.Listing).filter(db.Listing.id.in_(b.listing_ids), db.Listing.status == "live", db.Listing.decision == "donate").all()
    if not ls:
        raise HTTPException(404, "No open donations in selection")
    kg = sum(l.qty * l.kg_per_unit for l in ls)
    if kg > ngo.capacity_kg:
        raise HTTPException(409, f"Load {kg:.1f} kg exceeds vehicle capacity {ngo.capacity_kg:.0f} kg")
    vs = {v.id: v for v in s.query(db.Vendor).filter(db.Vendor.id.in_({l.vendor_id for l in ls}))}
    pts = [(vs[l.vendor_id].lat, vs[l.vendor_id].lng) for l in ls]
    depot = (ngo.lat, ngo.lng)
    t0 = time.perf_counter()
    order, km = routing.ortools_route(depot, pts, b.time_limit_ms)
    ms = (time.perf_counter() - t0) * 1000
    _, naive = routing.accept_order(depot, pts)
    return {"order": [ls[i].id for i in order], "km": round(km, 2), "naive_km": round(naive, 2), "kg": round(kg, 2),
            "solve_ms": round(ms, 1), "impact": imp.impact(kg, km)}


@app.post("/pickups/confirm")
def confirm(b: PlanIn, s=Depends(session), tok=Depends(auth("ngo", "admin"))):
    r = plan(b, s, tok)
    p = db.Pickup(ngo_id=b.ngo_id, km=r["km"], naive_km=r["naive_km"], kg=r["kg"])
    s.add(p); s.flush()
    s.query(db.Listing).filter(db.Listing.id.in_(b.listing_ids)).update({"status": "claimed", "pickup_id": p.id}, synchronize_session=False)
    s.commit(); invalidate()
    return {"pickup_id": p.id, **r}


class OrderIn(BaseModel):
    listing_id: int
    qty: float = Field(gt=0)


@app.post("/orders")
def order(b: OrderIn, s=Depends(session), tok=Depends(auth("customer", "admin"))):
    l = s.get(db.Listing, b.listing_id)
    if not l or l.status != "live" or l.decision != "sell":
        raise HTTPException(404, "Listing not available")
    if b.qty > l.qty:
        raise HTTPException(409, "Only %.0f left" % l.qty)
    l.qty -= b.qty
    if l.qty <= 0:
        l.status = "sold"
    o = db.Order(listing_id=l.id, qty=b.qty, total=round(b.qty * l.price, 2), kg=round(b.qty * l.kg_per_unit, 2), code=str(random.randint(1000, 9999)))
    s.add(o); s.commit(); invalidate()
    return {"order_id": o.id, "code": o.code, "total": o.total}


def _impact(s):
    sold = s.query(db.Order).all()
    kg_sold = sum(o.kg for o in sold)
    pk = s.query(db.Pickup).all()
    kg_don = sum(p.kg for p in pk); km = sum(p.km for p in pk)
    return {**imp.impact(kg_sold + kg_don, km), "kg_sold": round(kg_sold, 2), "kg_donated": round(kg_don, 2), "km": round(km, 2),
            "listings": s.query(db.Listing).count()}


@app.get("/impact")
def impact_ep(use_cache: bool = True, s=Depends(session)):
    return cached("impact", lambda: _impact(s), use_cache)


class SurplusIn(BaseModel):
    type_of_food: str; guests: int; event_type: str; quantity: float
    storage: str; purchase: str; season: str; prep: str; geo: str; pricing: str


@app.post("/forecast/surplus")
def forecast(b: SurplusIn):
    import pandas as pd
    m, cols = STATE["surplus"]
    row = dict.fromkeys(cols, 0.0)
    for c in (f"Type of Food_{b.type_of_food}", f"Event Type_{b.event_type}", f"Storage Conditions_{b.storage}", f"Purchase History_{b.purchase}",
              f"Seasonality_{b.season}", f"Preparation Method_{b.prep}", f"Geographical Location_{b.geo}", f"Pricing_{b.pricing}"):
        if c in row:
            row[c] = 1.0
    row["Number of Guests"] = b.guests; row["Quantity of Food"] = b.quantity
    return {"expected_waste": round(float(m.predict(pd.DataFrame([row])[cols])[0]), 1)}


@app.get("/health")
def health():
    return {"ok": True, "cache": STATS}


class DecideIn(BaseModel):
    category: str
    storage: str
    temp: float = Field(ge=5, le=50)
    hours: float = Field(ge=0, le=500)
    qty_kg: float = Field(gt=0)
    mrp: float = Field(ge=0)


@app.post("/decide")
def decide(b: DecideIn):
    """Stateless decision preview used by the Add-surplus screen (no database write)."""
    if b.category not in shelf.CATEGORIES or b.storage not in shelf.STORAGES:
        raise HTTPException(422, "Unknown category or storage")
    rem = ml.predict_remaining(STATE["shelf"], b.category, b.storage, b.temp, b.hours, b.qty_kg)
    d = shelf.decide_from_hours(rem)
    disc = shelf.discount_pct(rem) if d == "sell" else 0
    return {"remaining_h": round(rem, 1), "decision": d, "discount": disc, "price": round(b.mrp * (1 - disc / 100)), "source": "xgboost"}


class Pt(BaseModel):
    id: str
    lat: float
    lng: float


class RouteIn(BaseModel):
    depot: Pt
    stops: list[Pt]
    time_limit_ms: int = 200


@app.post("/route")
def route(b: RouteIn):
    """Stateless route planning used by the NGO screen."""
    if not b.stops:
        raise HTTPException(422, "No stops")
    depot = (b.depot.lat, b.depot.lng); pts = [(p.lat, p.lng) for p in b.stops]
    t0 = time.perf_counter(); order, km = routing.ortools_route(depot, pts, b.time_limit_ms); ms = (time.perf_counter() - t0) * 1000
    _, naive = routing.accept_order(depot, pts)
    return {"order": [b.stops[i].id for i in order], "km": round(km, 2), "naive_km": round(naive, 2), "solve_ms": round(ms, 1)}
