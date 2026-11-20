"""Model training and loading: shelf-life regressor (synthetic labels) and surplus regressor (real Kaggle data)."""
import json, os, time
import numpy as np, pandas as pd
import xgboost as xgb
from . import shelf

HERE = os.path.dirname(__file__)
MODEL_DIR = os.path.join(HERE, "..", "models")
os.makedirs(MODEL_DIR, exist_ok=True)
SHELF_PATH = os.path.join(MODEL_DIR, "shelf_xgb.json")
SURPLUS_PATH = os.path.join(MODEL_DIR, "surplus_xgb.json")
KAGGLE = os.environ.get("KAGGLE_CSV", "/mnt/user-data/uploads/food_wastage_data.csv")
SURPLUS_CATS = ["Type of Food", "Event Type", "Storage Conditions", "Purchase History",
                "Seasonality", "Preparation Method", "Geographical Location", "Pricing"]
SURPLUS_NUM = ["Number of Guests", "Quantity of Food"]
TARGET = "Wastage Food Amount"


def train_shelf(seed=42):
    d = shelf.synth(20000, seed)
    X = shelf.encode(d["category"], d["storage"], d["temp"], d["hours"], d["qty"])
    y = d["remaining"]
    m = xgb.XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.08, subsample=0.9,
                         colsample_bytree=0.9, n_jobs=1, random_state=seed)
    m.fit(X, y)
    m.save_model(SHELF_PATH)
    return m


def load_shelf():
    m = xgb.XGBRegressor(n_jobs=1)
    if not os.path.exists(SHELF_PATH):
        return train_shelf()
    m.load_model(SHELF_PATH)
    return m


def predict_remaining(model, cat, sto, temp, hours, qty):
    X = shelf.encode([cat], [sto], [temp], [hours], [qty])
    return float(model.predict(X)[0])


def surplus_frame(path=KAGGLE):
    df = pd.read_csv(path, encoding="utf-8-sig").drop_duplicates().reset_index(drop=True)
    X = pd.get_dummies(df[SURPLUS_CATS], dtype=float)
    X[SURPLUS_NUM] = df[SURPLUS_NUM].astype(float)
    return X, df[TARGET].astype(float), df


def train_surplus(seed=42):
    X, y, _ = surplus_frame()
    m = xgb.XGBRegressor(n_estimators=250, max_depth=4, learning_rate=0.05, subsample=0.9,
                         colsample_bytree=0.9, n_jobs=1, random_state=seed)
    m.fit(X, y)
    m.save_model(SURPLUS_PATH)
    json.dump(list(X.columns), open(os.path.join(MODEL_DIR, "surplus_cols.json"), "w"))
    return m, list(X.columns)


def load_surplus():
    if not os.path.exists(SURPLUS_PATH):
        return train_surplus()
    m = xgb.XGBRegressor(n_jobs=1); m.load_model(SURPLUS_PATH)
    return m, json.load(open(os.path.join(MODEL_DIR, "surplus_cols.json")))
