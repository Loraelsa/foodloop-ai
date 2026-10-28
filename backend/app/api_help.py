"""Customer care: star ratings for completed orders and a complaint desk handled by the admin."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Complaint, Listing, Notification, Review, User
from .security import current_user, require_role

help_router = APIRouter()

TOPICS = ("food_quality", "wrong_item", "vendor_issue", "pickup_problem", "payment", "account", "app_bug", "other")


# ---------------- ratings ----------------
class ReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(None, max_length=300)


@help_router.post("/listings/{listing_id}/review", status_code=201)
def rate_order(listing_id: int, body: ReviewIn, user: User = Depends(require_role("citizen")), db: Session = Depends(get_db)):
    l = db.get(Listing, listing_id)
    if not l or l.reserved_by != user.id:
        raise HTTPException(404, "Order not found")
    if l.status != "completed":
        raise HTTPException(409, "You can rate an order after you have collected it")
    if db.scalar(select(Review.id).where(Review.listing_id == l.id, Review.reviewer_id == user.id)):
        raise HTTPException(409, "You already rated this order")
    db.add(Review(listing_id=l.id, vendor_id=l.vendor_id, reviewer_id=user.id, stars=body.stars, comment=body.comment))
    db.commit()
    return {"ok": True}


@help_router.get("/my/reviews")
def my_reviews(user: User = Depends(require_role("citizen")), db: Session = Depends(get_db)):
    return {r.listing_id: r.stars for r in db.scalars(select(Review).where(Review.reviewer_id == user.id))}


# ---------------- complaints ----------------
class ComplaintIn(BaseModel):
    topic: Literal[TOPICS]  # type: ignore[valid-type]
    message: str = Field(min_length=10, max_length=1000)
    listing_id: int | None = None


def complaint_out(c: Complaint, with_user: bool = False):
    d = {"id": c.id, "topic": c.topic, "message": c.message, "status": c.status, "response": c.response,
         "listing_id": c.listing_id, "item_name": c.listing.item_name if c.listing else None,
         "created_at": c.created_at.isoformat() if c.created_at else None}
    if with_user:
        d["user"] = {"id": c.user.id, "name": c.user.name, "role": c.user.role, "email": c.user.email}
    return d


@help_router.post("/complaints", status_code=201)
def raise_complaint(body: ComplaintIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "admin":
        raise HTTPException(403, "Admins answer complaints; they do not raise them")
    if body.listing_id is not None:
        l = db.get(Listing, body.listing_id)
        if not l:
            raise HTTPException(404, "Order not found")
        mine = user.id in (l.vendor_id, l.reserved_by) or (l.pickup_id is not None and user.role == "ngo")
        if not mine:
            raise HTTPException(403, "You can only raise a complaint about your own orders")
    c = Complaint(user_id=user.id, listing_id=body.listing_id, topic=body.topic, message=body.message.strip())
    db.add(c)
    db.commit()
    return complaint_out(c)


@help_router.get("/complaints/mine")
def my_complaints(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Complaint).where(Complaint.user_id == user.id).order_by(Complaint.id.desc()).limit(50)).all()
    return [complaint_out(c) for c in rows]


admin_only = require_role("admin")


@help_router.get("/admin/complaints")
def all_complaints(admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Complaint).order_by(Complaint.status == "resolved", Complaint.id.desc()).limit(200)).all()
    return [complaint_out(c, with_user=True) for c in rows]


class ReplyIn(BaseModel):
    status: Literal["in_review", "resolved"]
    response: str = Field(min_length=3, max_length=1000)


@help_router.post("/admin/complaints/{complaint_id}/reply")
def reply(complaint_id: int, body: ReplyIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    c = db.get(Complaint, complaint_id)
    if not c:
        raise HTTPException(404, "Complaint not found")
    c.status, c.response = body.status, body.response.strip()
    db.add(Notification(user_id=c.user_id, kind="complaint", message=f"Your complaint #{c.id} is now {body.status.replace('_', ' ')}.", listing_id=c.listing_id))
    db.commit()
    return complaint_out(c, with_user=True)
