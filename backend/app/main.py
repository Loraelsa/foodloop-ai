from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import select

from .api import router
from .config import ADMIN_EMAIL, ADMIN_PASSWORD, FRONTEND_DIST
from .db import Base, SessionLocal, engine
from .metrics import LatencyMiddleware
from .models import Setting, User
from .security import hash_password


def seed_admin(db):
    if not db.scalar(select(User).where(User.email == ADMIN_EMAIL)):
        db.add(User(name="FoodLoop Admin", email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD),
                    role="admin", verified=True))
        db.commit()
        print(f"[FoodLoop] Admin account created: {ADMIN_EMAIL}  (password: ADMIN_PASSWORD in .env, or backend/.local_secrets.json)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    from .ml.engine import get_model, set_margin
    get_model()  # warm the model so the first request is not slow
    with SessionLocal() as db:
        seed_admin(db)
        m = db.get(Setting, "safety_margin_h")
        if m:
            set_margin(float(m.value))   # calibrated margin survives restarts
    yield


app = FastAPI(title="FoodLoop AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)  # smaller payloads = less energy on the wire
app.add_middleware(LatencyMiddleware)
app.include_router(router)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else FRONTEND_DIST / "index.html")
