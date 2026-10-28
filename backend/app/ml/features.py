"""Feature definitions + the synthetic proxy-data generator.

IMPORTANT (be honest in the report): until pilot data from real vendors is collected, the training set is
SYNTHETIC. Shelf-life is generated from a simple food-science rule (base shelf life per category, storage
multiplier, Q10-style temperature factor) plus noise. Reported accuracy therefore shows the pipeline works
end-to-end; it is NOT evidence of real-world freshness accuracy. Replace `generate_dataset` with pilot /
Kaggle-derived data when available and re-run `python -m app.ml.train`.
"""
import numpy as np
import pandas as pd

CATEGORIES = ["cooked_meal", "bakery", "dairy", "produce", "packaged", "dessert"]
STORAGES = ["ambient", "refrigerated", "hot_held"]

# Hours of safe shelf life at 25 C, ambient storage (assumption table, documented for the viva).
BASE_SHELF_HOURS = {"cooked_meal": 8, "bakery": 30, "dairy": 10, "produce": 60, "packaged": 240, "dessert": 12}
STORAGE_MULT = {"ambient": 1.0, "refrigerated": 3.5, "hot_held": 1.6}

FEATURE_COLUMNS = (
    ["hours_since_prepared", "ambient_temp_c", "quantity_kg"]
    + [f"cat_{c}" for c in CATEGORIES]
    + [f"store_{s}" for s in STORAGES]
)

SELL_MIN_HOURS = 4.0     # enough time for a buyer to collect and eat it
DONATE_MIN_HOURS = 1.0   # enough time for an NGO pickup + same-day serving


def true_remaining_hours(category, storage, temp_c, hours_since):
    base = BASE_SHELF_HOURS[category] * STORAGE_MULT[storage]
    temp_factor = 2 ** ((25.0 - temp_c) / 10.0)  # every +10 C halves shelf life
    return base * temp_factor - hours_since


def decision_from_hours(hours):
    if hours >= SELL_MIN_HOURS:
        return "sell"
    if hours >= DONATE_MIN_HOURS:
        return "donate"
    return "compost"


def featurize(rows: pd.DataFrame) -> pd.DataFrame:
    """rows needs: category, storage, hours_since_prepared, ambient_temp_c, quantity_kg."""
    out = pd.DataFrame(index=rows.index)
    out["hours_since_prepared"] = rows["hours_since_prepared"].astype(float)
    out["ambient_temp_c"] = rows["ambient_temp_c"].astype(float)
    out["quantity_kg"] = rows["quantity_kg"].astype(float)
    for c in CATEGORIES:
        out[f"cat_{c}"] = (rows["category"] == c).astype(int)
    for s in STORAGES:
        out[f"store_{s}"] = (rows["storage"] == s).astype(int)
    return out[FEATURE_COLUMNS]


def generate_dataset(n=20000, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cat = rng.choice(CATEGORIES, n)
    storage = rng.choice(STORAGES, n, p=[0.55, 0.30, 0.15])
    temp = np.clip(rng.normal(29, 6, n), 10, 45)
    base = np.array([BASE_SHELF_HOURS[c] * STORAGE_MULT[s] for c, s in zip(cat, storage)])
    # vendors list items somewhere between 0 and ~1.3x of their safe life
    since = rng.uniform(0, 1.3, n) * base * 2 ** ((25 - temp) / 10)
    qty = np.round(rng.gamma(2.0, 3.0, n) + 0.5, 1)
    remaining = np.array([true_remaining_hours(c, s, t, h) for c, s, t, h in zip(cat, storage, temp, since)])
    # noise = unobservable factors (handling, humidity, recipe). Proportional so it is realistic.
    noisy = remaining + rng.normal(0, 0.06, n) * np.abs(base) + rng.normal(0, 0.4, n)
    df = pd.DataFrame(
        dict(category=cat, storage=storage, ambient_temp_c=temp, hours_since_prepared=since,
             quantity_kg=qty, remaining_hours=noisy)
    )
    df["decision"] = df["remaining_hours"].apply(decision_from_hours)
    return df
