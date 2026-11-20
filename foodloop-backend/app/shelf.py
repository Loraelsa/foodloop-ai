"""Shelf-life rule table, synthetic data generator and decision thresholds.

The rule table is a documented ASSUMPTION (safe hours at 25 C, room temperature),
used (a) as the label generator for the synthetic training set and (b) as the
fallback when the model file is missing. It is not measured spoilage data.
"""
import numpy as np

CATEGORIES = ["cooked", "bakery", "dairy", "produce", "sweets", "packaged"]
BASE_HOURS = {"cooked": 6, "bakery": 36, "dairy": 8, "produce": 48, "sweets": 24, "packaged": 240}
STORAGES = ["room", "fridge", "hot"]
STORAGE_FACTOR = {"room": 1.0, "fridge": 3.5, "hot": 1.6}
SELL_H, DONATE_H = 4.0, 1.0           # decision thresholds (hours of safe life remaining)
CLASSES = ["compost", "donate", "sell"]


def true_life(cat, sto, temp, noise=1.0):
    """Safe life in hours: base * storage factor * 0.5^((T-25)/10) * noise."""
    return BASE_HOURS[cat] * STORAGE_FACTOR[sto] * 0.5 ** ((temp - 25.0) / 10.0) * noise


def remaining(cat, sto, temp, hours, noise=1.0):
    return true_life(cat, sto, temp, noise) - hours


def decide_from_hours(rem):
    if rem >= SELL_H:
        return "sell"
    if rem >= DONATE_H:
        return "donate"
    return "compost"


def discount_pct(rem):
    """20 % at >= 24 h remaining rising linearly to 70 % at 4 h (design choice)."""
    t = min(1.0, max(0.0, (rem - SELL_H) / (24.0 - SELL_H)))
    return round((0.7 - 0.5 * t) * 100)


def synth(n=20000, seed=42):
    """Synthetic listings. Returns dict of numpy arrays (features + hidden truth)."""
    rng = np.random.default_rng(seed)
    cat = rng.choice(CATEGORIES, n)
    sto = rng.choice(STORAGES, n, p=[0.55, 0.30, 0.15])
    qty = np.clip(rng.gamma(2.0, 3.2, n), 0.5, 40)
    temp = np.clip(rng.normal(29, 5, n), 10, 45)
    noise = rng.lognormal(0, 0.10, n)
    life = np.array([true_life(c, s, t, e) for c, s, t, e in zip(cat, sto, temp, noise)])
    hours = rng.uniform(0, 1.3, n) * life
    rem = life - hours
    return dict(category=cat, storage=sto, qty=qty, temp=temp, hours=hours, remaining=rem)


def encode(cat, sto, temp, hours, qty):
    """12-column feature vector: 6 + 3 one-hot, temp, hours, qty."""
    cat = np.asarray(cat); sto = np.asarray(sto)
    cols = [(cat == c).astype(float) for c in CATEGORIES] + [(sto == s).astype(float) for s in STORAGES]
    cols += [np.asarray(temp, float), np.asarray(hours, float), np.asarray(qty, float)]
    return np.column_stack(cols)


FEATURE_NAMES = [f"cat_{c}" for c in CATEGORIES] + [f"sto_{s}" for s in STORAGES] + ["temp_c", "hours_since_prep", "qty_kg"]
