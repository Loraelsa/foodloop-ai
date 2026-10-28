"""Retrain the freshness model with REAL reported outcomes blended into the synthetic base data.

Usage:  python -m app.ml.retrain            (reads the app database, writes a new model artifact)

How real outcomes become training rows (the labels are interval-censored, so we state the assumption openly):
  * spoiled  -> the item was NOT safe when handed over, so its remaining life was <= 0: target = -1.0 h (Compost class).
  * fine     -> the item was safe at least until handover, so the prediction made at listing time is kept as the target.
Real rows get weight REAL_WEIGHT so a few hundred of them can shift a model trained on 20,000 synthetic rows.
Compare `before` and `after` on the reported items printed at the end; keep the new model only if it improves.
"""
import json
import sys

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from xgboost import XGBRegressor

from ..db import SessionLocal
from ..models import Listing, Outcome
from . import engine as _engine
from .features import decision_from_hours, featurize, generate_dataset
from .train import ART

REAL_WEIGHT = 20.0
MIN_REAL = 30


def load_real(db) -> pd.DataFrame:
    rows = db.execute(select(Listing, func.max((Outcome.verdict == "spoiled").cast(__import__("sqlalchemy").Integer)))
                      .join(Outcome, Outcome.listing_id == Listing.id).group_by(Listing.id)).all()
    recs = [dict(category=l.category, storage=l.storage, hours_since_prepared=l.hours_since_prepared,
                 ambient_temp_c=l.ambient_temp_c, quantity_kg=l.quantity_kg,
                 predicted=l.remaining_hours, spoiled=int(s)) for l, s in rows]
    return pd.DataFrame(recs)


def main(db=None, out_path=None, n_synth=20000):
    own = db is None
    db = db or SessionLocal()
    try:
        real = load_real(db)
    finally:
        if own:
            db.close()
    if len(real) < MIN_REAL:
        print(f"Only {len(real)} reported outcomes; need {MIN_REAL}. Nothing retrained.")
        return {"status": "insufficient_data", "n_real": len(real)}
    real["remaining_hours"] = np.where(real.spoiled == 1, -1.0, real.predicted)
    synth = generate_dataset(n_synth)
    X = pd.concat([featurize(synth), featurize(real)], ignore_index=True)
    y = np.concatenate([synth["remaining_hours"].values, real["remaining_hours"].values])
    w = np.concatenate([np.ones(len(synth)), np.full(len(real), REAL_WEIGHT)])

    def bad_rate(model):  # share of reported-spoiled items the model would still have distributed
        p = model.predict(featurize(real))
        dist = np.array([decision_from_hours(h) != "compost" for h in p])
        sp = real.spoiled.values == 1
        return round(float((dist & sp).sum() / max(dist.sum(), 1)), 4)

    before = bad_rate(_engine.get_model())
    new = XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.1, n_jobs=1, tree_method="hist", random_state=1)
    new.fit(X, y, sample_weight=w)
    after = bad_rate(new)   # NOTE: measured on rows the model trained on; use a held-out split once n is large
    out_path = out_path or ART / "freshness_xgb.retrained.json"
    new.save_model(str(out_path))
    report = {"status": "ok", "n_real": int(len(real)), "n_spoiled": int(real.spoiled.sum()),
              "spoiled_share_of_distributed_before": before, "after": after, "artifact": str(out_path)}
    (ART / "retrain_report.json").write_text(json.dumps(report, indent=2))
    print(report)
    print("To adopt: copy the .retrained.json over freshness_xgb.json and restart (or call engine.reload_model()).")
    return report


if __name__ == "__main__":
    sys.exit(0 if main().get("status") in ("ok", "insufficient_data") else 1)
