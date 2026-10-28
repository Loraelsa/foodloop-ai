"""Central configuration. Every value can be overridden with an environment variable."""
import json
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file():
    """Tiny .env reader (KEY=VALUE per line) so no extra package is needed. Real environment variables win."""
    for p in (BASE_DIR.parent / ".env", BASE_DIR / ".env"):
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()
_LOCAL_SECRETS = BASE_DIR / ".local_secrets.json"   # git-ignored; holds values generated on this machine only


def local_secret(name: str, nbytes: int = 24) -> str:
    """Return a random secret generated once on this machine and remembered in a git-ignored file.
    Nothing secret is ever stored in the source code."""
    data = json.loads(_LOCAL_SECRETS.read_text()) if _LOCAL_SECRETS.is_file() else {}
    if name not in data:
        data[name] = secrets.token_urlsafe(nbytes)
        _LOCAL_SECRETS.write_text(json.dumps(data, indent=2))
    return data[name]


SECRET_KEY = os.getenv("SECRET_KEY") or local_secret("SECRET_KEY", 32)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'foodloop.db'}")
# Render/Heroku style URLs start with postgres:// - SQLAlchemy needs a driver name.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "24"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "app" / "ml" / "artifacts" / "freshness_xgb.json"))
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))

# ---- Impact assumptions (each is sourced; see the paper's reference list) ----
# FAO (2013) Food Wastage Footprint: 3.3 Gt CO2e / 1.3 Gt of food wasted per year = 2.54 kg CO2e per kg.
CO2E_PER_KG_FOOD = float(os.getenv("CO2E_PER_KG_FOOD", "2.5"))
# UK BEIS/DEFRA 2023 conversion factors: average diesel van (<= 3.5 t) = 0.231 kg CO2e per km.
EMISSION_KG_PER_KM = float(os.getenv("EMISSION_KG_PER_KM", "0.231"))
# WRAP guidance on meal equivalents: one meal = 420 g.
KG_PER_MEAL = float(os.getenv("KG_PER_MEAL", "0.42"))
# Straight-line -> road distance multiplier used by the router.
ROAD_FACTOR = float(os.getenv("ROAD_FACTOR", "1.3"))

IMPACT_CACHE_SECONDS = int(os.getenv("IMPACT_CACHE_SECONDS", "30"))

# ---- Trust & safety ----
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@foodloop.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or local_secret("ADMIN_PASSWORD", 9)   # set it in .env, or read the generated one
RATE_LIMIT_AUTH = int(os.getenv("RATE_LIMIT_AUTH", "10"))         # login/register attempts per minute per IP
RATE_LIMIT_API = int(os.getenv("RATE_LIMIT_API", "240"))          # all other API calls per minute per IP
NOTIFY_RADIUS_KM = float(os.getenv("NOTIFY_RADIUS_KM", "25"))     # NGOs within this radius are told about a donation
MAX_PHOTO_BYTES = int(os.getenv("MAX_PHOTO_BYTES", str(1_500_000)))

# ---- Routing ----
# OSRM table service for real road distances. Empty string disables it (haversine x ROAD_FACTOR is used instead).
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
OSRM_TIMEOUT_S = float(os.getenv("OSRM_TIMEOUT_S", "2.5"))
