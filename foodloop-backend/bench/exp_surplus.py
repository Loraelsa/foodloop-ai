"""Experiment 2: surplus (waste amount) regression on the REAL Kaggle restaurant-wastage data, 5-fold CV."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.model_selection import KFold
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from app import ml

raw = pd.read_csv(ml.KAGGLE, encoding="utf-8-sig")
X, y, df = ml.surplus_frame()
print("raw", raw.shape, "after dedup", df.shape, "dups", len(raw) - len(df))
q = df["Quantity of Food"].values; ratio = (y / df["Quantity of Food"]).mean()
models = {
    "Mean baseline": None, "Fixed-ratio baseline": None,
    "Linear regression": lambda: LinearRegression(),
    "Random forest": lambda: RandomForestRegressor(n_estimators=200, max_depth=10, n_jobs=1, random_state=42),
    "XGBoost (deployed)": lambda: xgb.XGBRegressor(n_estimators=250, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, n_jobs=1, random_state=42),
}
kf = KFold(5, shuffle=True, random_state=42); out = {}
for name, mk in models.items():
    rm, ma, r2, tt, li = [], [], [], [], []
    for tr, te in kf.split(X):
        if name == "Mean baseline": p = np.full(len(te), y.iloc[tr].mean()); t = 0
        elif name == "Fixed-ratio baseline":
            r = (y.iloc[tr] / df["Quantity of Food"].iloc[tr]).mean(); p = r * q[te]; t = 0
        else:
            m = mk(); s = time.process_time(); m.fit(X.iloc[tr], y.iloc[tr]); t = time.process_time() - s; p = m.predict(X.iloc[te])
        rm.append(np.sqrt(mean_squared_error(y.iloc[te], p))); ma.append(mean_absolute_error(y.iloc[te], p)); r2.append(r2_score(y.iloc[te], p)); tt.append(t)
    out[name] = dict(rmse=[float(np.mean(rm)), float(np.std(rm))], mae=[float(np.mean(ma)), float(np.std(ma))], r2=[float(np.mean(r2)), float(np.std(r2))], train_cpu_s=float(np.mean(tt)))
    print(name, {k: (np.round(v, 3).tolist() if isinstance(v, list) else round(v, 3)) for k, v in out[name].items()})
# final fit for feature importance
m = xgb.XGBRegressor(n_estimators=250, max_depth=4, learning_rate=0.05, subsample=0.9, colsample_bytree=0.9, n_jobs=1, random_state=42).fit(X, y)
imp = pd.Series(m.feature_importances_, index=X.columns)
groups = {}
for c in X.columns:
    g = c.split("_")[0] if c in ("Number of Guests", "Quantity of Food") else c.rsplit("_", 1)[0]
    g = c if c in ("Number of Guests", "Quantity of Food") else [k for k in ml.SURPLUS_CATS if c.startswith(k + "_")][0]
    groups[g] = groups.get(g, 0) + float(imp[c])
res = dict(n_raw=int(len(raw)), n_clean=int(len(df)), dups=int(len(raw) - len(df)), models=out, importance=dict(sorted(groups.items(), key=lambda kv: -kv[1])),
           mean_waste=float(y.mean()), mean_ratio=float(ratio), waste_min=float(y.min()), waste_max=float(y.max()),
           corr_guests=float(np.corrcoef(df["Number of Guests"], y)[0, 1]), corr_qty=float(np.corrcoef(df["Quantity of Food"], y)[0, 1]),
           by_type=df.groupby("Type of Food")[ml.TARGET].mean().round(2).to_dict(), by_event=df.groupby("Event Type")[ml.TARGET].mean().round(2).to_dict(),
           by_storage=df.groupby("Storage Conditions")[ml.TARGET].mean().round(2).to_dict(), by_geo=df.groupby("Geographical Location")[ml.TARGET].mean().round(2).to_dict())
json.dump(res, open(os.path.join(os.path.dirname(__file__), "out", "surplus.json"), "w"), indent=1)
print(res["importance"]); print(res["by_type"], res["by_storage"], res["corr_guests"], res["corr_qty"], res["mean_ratio"])
