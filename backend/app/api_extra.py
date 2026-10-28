"""Second router: trust & safety, notifications, photos, QR handover, and the outcome feedback loop."""
import csv
import io
from typing import Literal

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, metrics
from .api import listing_out, require_verified, user_out
from .db import get_db
from .ml import engine
from .models import Listing, Notification, Outcome, Pickup, Setting, User
from .ratelimit import _check, limit_api
from .security import current_user, require_role

extra = APIRouter()


# ======================= notifications =======================
@extra.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)
                      .order_by(Notification.id.desc()).limit(30)).all()
    return {"unread": sum(1 for n in rows if not n.read),
            "items": [{"id": n.id, "kind": n.kind, "message": n.message, "listing_id": n.listing_id,
                       "read": n.read, "created_at": n.created_at.isoformat()} for n in rows]}


@extra.post("/notifications/read")
def mark_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {"ok": True}


# ======================= photos =======================
_MAGIC = {b"\xff\xd8\xff": "jpeg", b"\x89PNG": "png"}


def _sniff(data: bytes) -> bool:
    return data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


@extra.post("/listings/{listing_id}/photo")
async def upload_photo(listing_id: int, file: UploadFile = File(...), user: User = Depends(require_role("vendor")),
                       db: Session = Depends(get_db)):
    _check(f"photo:{user.id}", 20)   # at most 20 uploads a minute per vendor
    l = db.get(Listing, listing_id)
    if not l or l.vendor_id != user.id:
        raise HTTPException(404, "Listing not found")
    data = await file.read(config.MAX_PHOTO_BYTES + 1)
    if len(data) > config.MAX_PHOTO_BYTES:
        raise HTTPException(413, f"Photo is larger than {config.MAX_PHOTO_BYTES // 1000} KB")
    if not _sniff(data):   # trust the bytes, not the filename or the declared content type
        raise HTTPException(415, "Only JPEG, PNG or WebP photos are accepted")
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        img.thumbnail((800, 800))          # re-encoding also strips EXIF/GPS and any embedded payload
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80, optimize=True)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "That file is not a readable image")
    l.photo, l.has_photo = buf.getvalue(), True
    db.commit()
    return {"ok": True, "bytes": len(l.photo)}


@extra.get("/listings/{listing_id}/photo")
def get_photo(listing_id: int, db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or not l.has_photo or not l.photo:
        raise HTTPException(404, "No photo")
    return Response(l.photo, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


# ======================= QR / handover =======================
def _holder_can_see_code(l: Listing, user: User, db: Session) -> bool:
    if l.decision == "sell":
        return l.reserved_by == user.id
    if l.decision == "donate" and l.pickup_id:
        p = db.get(Pickup, l.pickup_id)
        return bool(p and p.ngo_id == user.id)
    return False


@extra.get("/listings/{listing_id}/qr")
def qr(listing_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or not _holder_can_see_code(l, user, db) or l.status == "completed":
        raise HTTPException(404, "No active pickup code for you on this item")
    img = qrcode.make(l.pickup_code, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return {"code": l.pickup_code, "svg": buf.getvalue().decode()}


@extra.get("/my/items")
def my_items(user: User = Depends(require_role("citizen", "ngo")), db: Session = Depends(get_db)):
    """Items I am due to collect (citizen reservations or NGO accepted donations), each with its handover code."""
    if user.role == "citizen":
        q = select(Listing).where(Listing.reserved_by == user.id)
    else:
        q = select(Listing).join(Pickup, Listing.pickup_id == Pickup.id).where(Pickup.ngo_id == user.id)
    rows = db.scalars(q.order_by(Listing.id.desc()).limit(50)).all()
    out = []
    for l in rows:
        d = listing_out(l, user)
        d["pickup_code"] = l.pickup_code if l.status != "completed" else None
        d["reported"] = bool(db.scalar(select(Outcome.id).where(Outcome.listing_id == l.id, Outcome.reporter_id == user.id)))
        out.append(d)
    return out


class HandoverIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


@extra.post("/handover")
def handover(body: HandoverIn, user: User = Depends(require_role("vendor")), db: Session = Depends(get_db)):
    """Vendor scans / types the buyer's or NGO's code. Proves the food really changed hands."""
    _check(f"handover:{user.id}", 30)
    code = body.code.strip().upper()
    l = db.scalar(select(Listing).where(Listing.pickup_code == code, Listing.vendor_id == user.id))
    if not l:
        raise HTTPException(404, "That code does not match any of your items")
    if l.status == "completed":
        raise HTTPException(409, "This item was already handed over")
    if l.status not in ("reserved", "accepted"):
        raise HTTPException(409, "Nobody has reserved or accepted this item yet")
    l.status = "completed"
    db.flush()   # sessions use autoflush=False, so make the count below see this change
    if l.pickup_id:   # last stop of an NGO pickup done -> close the pickup
        left = db.scalar(select(func.count(Listing.id)).where(Listing.pickup_id == l.pickup_id, Listing.status != "completed"))
        if not left:
            p = db.get(Pickup, l.pickup_id)
            p.status = "completed"
    db.commit()
    metrics.invalidate()
    return listing_out(l)


# ======================= outcome feedback loop =======================
class OutcomeIn(BaseModel):
    verdict: Literal["fine", "spoiled"]
    note: str | None = Field(None, max_length=300)


@extra.post("/listings/{listing_id}/outcome", status_code=201)
def report_outcome(listing_id: int, body: OutcomeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l:
        raise HTTPException(404, "Listing not found")
    p = db.get(Pickup, l.pickup_id) if l.pickup_id else None
    allowed = (user.id == l.vendor_id) or (l.reserved_by == user.id) or (p is not None and p.ngo_id == user.id)
    if not allowed:
        raise HTTPException(403, "Only the vendor, the buyer or the collecting NGO can report on this item")
    if l.status != "completed":
        raise HTTPException(409, "Report after the item has been handed over")
    if db.scalar(select(Outcome.id).where(Outcome.listing_id == l.id, Outcome.reporter_id == user.id)):
        raise HTTPException(409, "You already reported on this item")
    db.add(Outcome(listing_id=l.id, reporter_id=user.id, verdict=body.verdict, note=body.note))
    db.commit()
    return {"ok": True}


# ======================= admin =======================
admin_only = require_role("admin")


@extra.get("/admin/pending")
def pending(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.role.in_(("vendor", "ngo")), User.verified.is_(False)).order_by(User.id)).all()
    return [user_out(u) for u in rows]


@extra.get("/admin/users")
def all_users(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id.desc()).limit(200))]


class VerifyIn(BaseModel):
    approve: bool


@extra.post("/admin/users/{user_id}/verify")
def verify(user_id: int, body: VerifyIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.role not in ("vendor", "ngo"):
        raise HTTPException(404, "Vendor or NGO account not found")
    u.verified = body.approve
    db.commit()
    return user_out(u)


def _outcome_rows(db: Session):
    """One row per reported listing: spoiled if anybody reported it spoiled."""
    rows = db.execute(select(Listing, func.max((Outcome.verdict == "spoiled").cast(Integer_))).join(
        Outcome, Outcome.listing_id == Listing.id).group_by(Listing.id)).all()
    return [(l, bool(s)) for l, s in rows]


from sqlalchemy import Integer as Integer_  # noqa: E402


@extra.get("/admin/outcomes.csv")
def outcomes_csv(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["listing_id", "category", "storage", "ambient_temp_c", "hours_since_prepared", "quantity_kg",
                "predicted_remaining_h", "decision", "spoiled"])
    for l, spoiled in _outcome_rows(db):
        w.writerow([l.id, l.category, l.storage, l.ambient_temp_c, l.hours_since_prepared, l.quantity_kg,
                    l.remaining_hours, l.decision, int(spoiled)])
    return Response(buf.getvalue(), media_type="text/csv")


GRID = [i * 0.25 for i in range(0, 17)]   # candidate margins 0 .. 4 h
MIN_OUTCOMES = 30


def calibrate_margin(pairs, target=0.05):
    """Smallest margin h such that, among items still distributed (remaining - h >= 1 h), at most `target` were spoiled.

    pairs = [(predicted_remaining_hours_at_listing_time, spoiled_bool)]. Honest limits: needs >= MIN_OUTCOMES reports,
    and only items that were distributed have an outcome, so a larger margin can be assessed but a smaller one
    (than the margin in force when the item was listed) cannot be observed.
    """
    if len(pairs) < MIN_OUTCOMES:
        return {"status": "insufficient_data", "n": len(pairs), "needed": MIN_OUTCOMES}
    table = []
    for h in GRID:
        kept = [(r, s) for r, s in pairs if r - h >= 1.0]
        rate = (sum(s for _, s in kept) / len(kept)) if kept else 0.0
        table.append({"margin_h": h, "distributed": len(kept), "spoiled_rate": round(rate, 4)})
    chosen = next((t for t in table if t["spoiled_rate"] <= target), table[-1])
    return {"status": "ok", "n": len(pairs), "target": target, "recommended_margin_h": chosen["margin_h"], "table": table}


@extra.get("/admin/outcome-stats")
def outcome_stats(target: float = 0.05, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    pairs = [(l.remaining_hours, s) for l, s in _outcome_rows(db)]
    res = calibrate_margin(pairs, target)
    res["current_margin_h"] = engine.get_margin()
    res["spoiled_total"] = sum(1 for _, s in pairs if s)
    return res


@extra.post("/admin/calibrate")
def apply_calibration(target: float = 0.05, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    pairs = [(l.remaining_hours, s) for l, s in _outcome_rows(db)]
    res = calibrate_margin(pairs, target)
    if res["status"] == "ok":
        m = res["recommended_margin_h"]
        row = db.get(Setting, "safety_margin_h")
        if row:
            row.value = str(m)
        else:
            db.add(Setting(key="safety_margin_h", value=str(m)))
        db.commit()
        engine.set_margin(m)
    res["current_margin_h"] = engine.get_margin()
    return res
