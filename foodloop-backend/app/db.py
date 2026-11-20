from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime as dt, os

DB_URL = os.environ.get("FOODLOOP_DB", "sqlite:///foodloop.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


class Vendor(Base):
    __tablename__ = "vendors"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    locality = Column(String(60))
    lat = Column(Float); lng = Column(Float)
    status = Column(String(12), default="approved")


class Ngo(Base):
    __tablename__ = "ngos"
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    lat = Column(Float); lng = Column(Float)
    capacity_kg = Column(Float, default=120)
    status = Column(String(12), default="verified")


class Listing(Base):
    __tablename__ = "listings"
    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), index=True)
    item = Column(String(80)); category = Column(String(12)); storage = Column(String(8))
    temp = Column(Float); hours = Column(Float); qty = Column(Float); unit = Column(String(12))
    kg_per_unit = Column(Float); mrp = Column(Float)
    remaining = Column(Float); decision = Column(String(8), index=True); discount = Column(Integer)
    price = Column(Float); status = Column(String(10), default="live", index=True)
    created = Column(DateTime, default=dt.datetime.utcnow)
    expires = Column(DateTime)
    pickup_id = Column(Integer, ForeignKey("pickups.id"), nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), index=True)
    qty = Column(Float); total = Column(Float); kg = Column(Float)
    code = Column(String(4)); status = Column(String(10), default="placed")
    created = Column(DateTime, default=dt.datetime.utcnow)


class Pickup(Base):
    __tablename__ = "pickups"
    id = Column(Integer, primary_key=True)
    ngo_id = Column(Integer, ForeignKey("ngos.id"), index=True)
    km = Column(Float); naive_km = Column(Float); kg = Column(Float)
    status = Column(String(10), default="planned")
    created = Column(DateTime, default=dt.datetime.utcnow)


Index("ix_listing_live_decision", Listing.status, Listing.decision)


def init(seed=True):
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if seed and s.query(Vendor).count() == 0:
            from .seed import VENDORS, NGOS
            s.add_all([Vendor(**v) for v in VENDORS]); s.add_all([Ngo(**n) for n in NGOS]); s.commit()
