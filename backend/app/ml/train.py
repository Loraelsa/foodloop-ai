"""Train + benchmark the freshness model.  Usage:  python -m app.ml.train"""
import json
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from .features import FEATURE_COLUMNS, decision_from_hours, featurize, generate_dataset

ART = Path(__file__).resolve().parent / "artifacts"


def evaluate(name, model, Xtr, ytr, Xte, yte, dec_te, save_to=None):
    t0 = time.perf_counter()
    model.fit(Xtr, ytr)
    train_s = time.perf_counter() - t0
    # single-row inference latency, the number that matters for an API
    row = Xte.iloc[[0]]
    model.predict(row)
    reps = 200
    t0 = time.perf_counter()
    for _ in range(reps):
        model.predict(row)
    single_ms = (time.perf_counter() - t0) / reps * 1000
    pred = model.predict(Xte)
    dec_pred = [decision_from_hours(h) for h in pred]
    size_kb = None
    if save_to is not None:
        model.save_model(str(save_to))
        size_kb = save_to.stat().st_size / 1024
    return {
        "model": name,
        "rmse_hours": round(float(np.sqrt(mean_squared_error(yte, pred))), 3),
        "r2": round(float(r2_score(yte, pred)), 4),
        "decision_accuracy": round(float(accuracy_score(dec_te, dec_pred)), 4),
        "decision_macro_f1": round(float(f1_score(dec_te, dec_pred, average="macro")), 4),
        "train_seconds": round(train_s, 3),
        "inference_ms_single_row": round(single_ms, 3),
        "model_size_kb": None if size_kb is None else round(size_kb, 1),
    }


def main(n=20000):
    ART.mkdir(exist_ok=True)
    df = generate_dataset(n)
    X = featurize(df)
    y = df["remaining_hours"]
    Xtr, Xte, ytr, yte, _, dtr = train_test_split(X, y, df["decision"], test_size=0.2, random_state=42)

    results = [
        evaluate("LinearRegression (baseline)", LinearRegression(), Xtr, ytr, Xte, yte, dtr),
        evaluate("RandomForest", RandomForestRegressor(n_estimators=120, max_depth=12, n_jobs=1, random_state=1),
                 Xtr, ytr, Xte, yte, dtr),
        evaluate("XGBoost (deployed)", XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.1,
                                                   n_jobs=1, tree_method="hist", random_state=1),
                 Xtr, ytr, Xte, yte, dtr, save_to=ART / "freshness_xgb.json"),
    ]
    out = {"n_rows": n, "data_source": "synthetic proxy (rule-based shelf life + noise)",
           "features": FEATURE_COLUMNS, "results": results}
    (ART / "training_report.json").write_text(json.dumps(out, indent=2))
    for r in results:
        print(r)
    return out


if __name__ == "__main__":
    main()
