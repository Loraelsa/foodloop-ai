import os
import tempfile
import uuid

# Use a throwaway DB for tests - must be set before the app is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SECRET_KEY"] = "test-only-key-not-a-real-secret-0123456789"
os.environ["ADMIN_PASSWORD"] = "test-admin-" + os.urandom(6).hex()
TEST_PW = "tp-" + uuid.uuid4().hex          # random per run: no password is stored in the repository
os.environ["OSRM_URL"] = ""            # tests must not depend on the network
os.environ["RATE_LIMIT_AUTH"] = "100000"
os.environ["RATE_LIMIT_API"] = "1000000"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def make_user(client, role, name=None, lat=28.6139, lon=77.2090, verified=True):
    import uuid
    email = f"{role}-{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/api/auth/register", json={"name": name or f"{role} user", "email": email,
                                                "password": TEST_PW, "role": role, "lat": lat, "lon": lon})
    assert r.status_code == 201, r.text
    user = r.json()["user"]
    if verified and role in ("vendor", "ngo"):   # the admin approval step, done directly for test speed
        from app.db import SessionLocal
        from app.models import User
        with SessionLocal() as db:
            db.get(User, user["id"]).verified = True
            db.commit()
        user["verified"] = True
    return {"Authorization": f"Bearer {r.json()['token']}"}, user


def admin_headers(client):
    from app.config import ADMIN_EMAIL, ADMIN_PASSWORD
    r = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
