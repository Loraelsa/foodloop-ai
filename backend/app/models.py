from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10))  # vendor | citizen | ngo | admin
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # vendors/NGOs need admin approval
    lat: Mapped[float] = mapped_column(Float, default=28.6139)
    lon: Mapped[float] = mapped_column(Float, default=77.2090)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30))
    quantity_kg: Mapped[float] = mapped_column(Float)
    mrp: Mapped[float] = mapped_column(Float, default=0.0)  # full price for the whole lot, INR
    hours_since_prepared: Mapped[float] = mapped_column(Float)
    storage: Mapped[str] = mapped_column(String(20))
    ambient_temp_c: Mapped[float] = mapped_column(Float, default=28.0)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # ML output
    remaining_hours: Mapped[float] = mapped_column(Float)
    freshness_score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(10))  # sell | donate | compost
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="available")  # available|reserved|accepted|completed
    reserved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    pickup_id: Mapped[int | None] = mapped_column(ForeignKey("pickups.id"), nullable=True)
    pickup_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)  # handover code / QR payload
    photo: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))       # loaded only when asked for
    has_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vendor: Mapped[User] = relationship(foreign_keys=[vendor_id])

    __table_args__ = (
        Index("ix_listing_status_decision", "status", "decision"),
        Index("ix_listing_lat_lon", "lat", "lon"),  # serves the bounding-box pre-filter for nearby searches
    )


class Pickup(Base):
    __tablename__ = "pickups"
    id: Mapped[int] = mapped_column(primary_key=True)
    ngo_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned | completed
    route: Mapped[dict] = mapped_column(JSON)  # ordered stops + distance stats
    total_kg: Mapped[float] = mapped_column(Float, default=0.0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_km: Mapped[float] = mapped_column(Float, default=0.0)
    co2_saved_kg: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outcome(Base):
    """Ground truth reported after handover: was the food actually fine? This is the real-data feedback loop."""
    __tablename__ = "outcomes"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    verdict: Mapped[str] = mapped_column(String(10))  # fine | spoiled
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("listing_id", "reporter_id", name="uq_outcome_once"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(300))
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Tiny key/value store (e.g. the calibrated safety margin)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Review(Base):
    """A buyer's star rating of a completed order. One per listing and reviewer."""
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("listing_id", "reviewer_id", name="uq_review_once"),)


class Complaint(Base):
    """A problem raised by any user, optionally about one order. Admins answer and close it."""
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"), nullable=True)
    topic: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | in_review | resolved
    response: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    listing: Mapped["Listing | None"] = relationship(foreign_keys=[listing_id])
