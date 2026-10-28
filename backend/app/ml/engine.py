"""Runtime decision engine: freshness -> Sell / Donate / Compost + dynamic price."""
import pandas as pd
from xgboost import XGBRegressor

from ..config import MODEL_PATH
from .features import BASE_SHELF_HOURS, STORAGE_MULT, decision_from_hours, featurize

_model = None
_margin_h = 0.0   # calibrated from reported outcomes (see /api/admin/calibrate); subtracted before deciding


def get_margin() -> float:
    return _margin_h


def set_margin(h: float) -> None:
    global _margin_h
    _margin_h = max(0.0, float(h))


def reload_model() -> None:
    """Drop the cached model so the next request loads the latest artifact (used after retraining)."""
    global _model
    _model = None


def get_model() -> XGBRegressor:
    """Loaded once per process (lazy) - avoids re-loading on every request."""
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            from . import train
            train.main()
        m = XGBRegressor()
        m.load_model(str(MODEL_PATH))
        _model = m
    return _model


def discount_for(hours: float) -> float:
    """20% off with plenty of time left, rising to 70% as the item nears the sell cut-off."""
    urgency = 1 - min(max(hours, 0.0), 12.0) / 12.0
    return round(0.20 + 0.50 * urgency, 2)


def assess(category, storage, hours_since_prepared, ambient_temp_c, quantity_kg, mrp=0.0) -> dict:
    row = pd.DataFrame([dict(category=category, storage=storage, hours_since_prepared=hours_since_prepared,
                             ambient_temp_c=ambient_temp_c, quantity_kg=quantity_kg)])
    raw = float(get_model().predict(featurize(row))[0])
    remaining = raw - _margin_h   # conservative: the safety margin only ever moves items towards Donate/Compost
    decision = decision_from_hours(remaining)
    effective_life = BASE_SHELF_HOURS[category] * STORAGE_MULT[storage] * 2 ** ((25.0 - ambient_temp_c) / 10.0)
    freshness = max(0.0, min(1.0, remaining / effective_life)) if effective_life > 0 else 0.0
    discount = discount_for(remaining) if decision == "sell" else (1.0 if decision == "donate" else 0.0)
    price = round(mrp * (1 - discount), 2) if decision == "sell" else 0.0
    return {
        "remaining_hours": round(remaining, 2), "safety_margin_h": round(_margin_h, 2),
        "freshness_score": round(freshness, 3),
        "decision": decision,
        "discount_pct": round(discount * 100, 1) if decision == "sell" else 0.0,
        "price": price,
    }
