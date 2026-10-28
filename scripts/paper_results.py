"""Reproduces every number and figure in the research paper (EDA, model evaluation, benefit simulation).

Run from backend/:   python ../scripts/paper_results.py
Outputs: docs/paper_results.json and 300-dpi figures in docs/paper_figs/

Honest scope: the dataset is SYNTHETIC (see backend/app/ml/features.py). Ground-truth freshness classes come from
a documented shelf-life model, so absolute accuracy shows the pipeline works, not real-world accuracy. The simulation
compares *policies* on identical items, so the relative benefits are meaningful under the stated assumptions.
"""
import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, mean_squared_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import CO2E_PER_KG_FOOD, EMISSION_KG_PER_KM, KG_PER_MEAL, MODEL_PATH  # noqa: E402
from app.ml.engine import discount_for  # noqa: E402
from app.ml.features import (CATEGORIES, FEATURE_COLUMNS, STORAGES, decision_from_hours,  # noqa: E402
                             featurize, generate_dataset)
from app.routing import _matrix, plan_route, route_length_m  # noqa: E402

FIG = ROOT / "docs" / "paper_figs"
FIG.mkdir(parents=True, exist_ok=True)
OUT = {}

# ---------- style (validated reference palette, slots 1-3 + neutrals) ----------
BLUE, ORANGE, AQUA, VIOLET, YELLOW, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#eda100", "#8a8a85"
INK, MUTED, GRID = "#1b1b1a", "#52514e", "#e4e3df"
CLS = {"sell": BLUE, "donate": ORANGE, "compost": AQUA}
plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 9, "axes.titlesize": 9.5,
    "axes.labelsize": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.dpi": 100, "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.06,
})
W = 6.7  # inches = text width in the paper, so fonts print at true size


def save(fig, name):
    fig.savefig(FIG / name)
    plt.close(fig)


def panel(ax, tag):
    ax.text(-0.02, 1.04, tag, transform=ax.transAxes, fontsize=10, fontweight="bold", ha="right", va="bottom")


# =====================================================================================================
# 1. DATASET + EDA
# =====================================================================================================
df = generate_dataset(20000)
df["life_hours"] = df["remaining_hours"] + df["hours_since_prepared"]
rank = {"compost": 0, "donate": 1, "sell": 2}
OUT["dataset"] = {
    "n": len(df),
    "class_share": (df["decision"].value_counts(normalize=True) * 100).round(1).to_dict(),
    "by_category": {c: {"n": int((df.category == c).sum()),
                        **{d: round(float(((df.category == c) & (df.decision == d)).sum() / (df.category == c).sum() * 100), 1)
                           for d in ("sell", "donate", "compost")}} for c in CATEGORIES},
    "by_storage": {s: int((df.storage == s).sum()) for s in STORAGES},
    "quantity_kg": df.quantity_kg.describe().round(2).to_dict(),
    "temp_c": df.ambient_temp_c.describe().round(1).to_dict(),
    "hours_since_prepared": df.hours_since_prepared.describe().round(1).to_dict(),
    "remaining_hours": df.remaining_hours.describe().round(1).to_dict(),
}
LABEL = {"cooked_meal": "Cooked meal", "bakery": "Bakery", "dairy": "Dairy", "produce": "Fruit & veg",
         "packaged": "Packaged", "dessert": "Dessert"}
SLAB = {"ambient": "Room temp.", "refrigerated": "Refrigerated", "hot_held": "Kept hot"}

fig, axs = plt.subplots(2, 2, figsize=(W, 6.4))
# (a) decision mix per category
ax = axs[0, 0]
share = pd.crosstab(df.category, df.decision, normalize="index")[["sell", "donate", "compost"]] * 100
share = share.sort_values("compost")
left = np.zeros(len(share))
for d in ("sell", "donate", "compost"):
    ax.barh([LABEL[c] for c in share.index], share[d], left=left, color=CLS[d], edgecolor="white", linewidth=1.2, label=d.capitalize())
    for i, v in enumerate(share[d]):
        if v >= 7:
            ax.text(left[i] + v / 2, i, f"{v:.0f}", ha="center", va="center", color="white", fontsize=8, fontweight="bold")
    left += share[d].values
ax.set_xlim(0, 100); ax.set_xlabel("Share of listed items (%)"); ax.grid(axis="y", visible=False)
ax.set_title("Decision mix by food category"); ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.32), frameon=False)
panel(ax, "(a)")
# (b) median remaining hours by category x storage (log)
ax = axs[0, 1]
med = df.groupby(["category", "storage"]).life_hours.median().unstack()[STORAGES]
x = np.arange(len(CATEGORIES)); bw = 0.26
for k, (s, col) in enumerate(zip(STORAGES, (GRAY, VIOLET, YELLOW))):
    ax.bar(x + (k - 1) * bw, [med.loc[c, s] for c in CATEGORIES], bw, color=col, edgecolor="white", linewidth=0.8, label=SLAB[s])
ax.set_yscale("log"); ax.set_xticks(x); ax.set_xticklabels([LABEL[c] for c in CATEGORIES], fontsize=7.5, rotation=35, ha="right")
ax.set_ylabel("Median safe shelf life (h, log scale)"); ax.grid(axis="x", visible=False)
ax.set_title("Shelf life by category and storage"); ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.42), frameon=False)
panel(ax, "(b)")
# (c) temperature effect, cooked meals
ax = axs[1, 0]
cm = df[df.category == "cooked_meal"].copy()
cm["tb"] = pd.cut(cm.ambient_temp_c, np.arange(10, 50, 5), labels=np.arange(12.5, 47.5, 5))
for s, col in zip(STORAGES, (GRAY, VIOLET, YELLOW)):
    g = cm[cm.storage == s].groupby("tb", observed=True).life_hours.mean()
    ax.plot(g.index.astype(float), g.values, marker="o", color=col, linewidth=1.8, markersize=4.5, markeredgecolor="white")
    ax.lines[-1].set_label(SLAB[s])
ax.legend(frameon=False, fontsize=7.5); ax.set_xlim(10, 46); ax.set_xlabel("Ambient temperature (°C)"); ax.set_ylabel("Mean safe shelf life (h)")
ax.set_title("Shelf life vs temperature (cooked meals)", fontsize=9); panel(ax, "(c)")
# (d) spearman correlation
ax = axs[1, 1]
cdf = df[["hours_since_prepared", "ambient_temp_c", "quantity_kg", "remaining_hours"]].copy()
cdf["decision (ordinal)"] = df.decision.map(rank)
cdf.columns = ["Hours\nsince", "Temp.", "Qty", "Remain.\nhours", "Decision"]
corr = cdf.corr(method="spearman")
OUT["spearman"] = corr.round(3).rename(index=lambda s: s.replace("\n", " "), columns=lambda s: s.replace("\n", " ")).to_dict()
cmap = LinearSegmentedColormap.from_list("div", [ORANGE, "#f4f3f0", BLUE])
im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
ax.set_xticks(range(5)); ax.set_yticks(range(5)); ax.set_xticklabels(corr.columns, fontsize=7.2); ax.set_yticklabels(corr.index, fontsize=7.2)
for i in range(5):
    for j in range(5):
        v = corr.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8, color="white" if abs(v) > 0.6 else INK)
ax.grid(False); ax.set_title("Spearman correlation"); [s.set_visible(False) for s in ax.spines.values()]
cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03); cb.outline.set_visible(False); cb.ax.tick_params(labelsize=7.5)
panel(ax, "(d)")
fig.tight_layout(h_pad=2.2, w_pad=2.0)
save(fig, "eda.png")

# =====================================================================================================
# 2. MODEL EVALUATION (same 80/20 split as backend/app/ml/train.py)
# =====================================================================================================
X, y = featurize(df), df["remaining_hours"]
idx_tr, idx_te = train_test_split(np.arange(len(df)), test_size=0.2, random_state=42)
Xtr, Xte, ytr, yte = X.iloc[idx_tr], X.iloc[idx_te], y.iloc[idx_tr], y.iloc[idx_te]
dtr, dte = df.iloc[idx_tr].reset_index(drop=True), df.iloc[idx_te].reset_index(drop=True)
c_te = dte["decision"].map(rank).values
q_te = dte["quantity_kg"].values

xgb = XGBRegressor(); xgb.load_model(str(MODEL_PATH))   # the deployed model
rf = RandomForestRegressor(n_estimators=120, max_depth=12, n_jobs=1, random_state=1).fit(Xtr, ytr)
lr = LinearRegression().fit(Xtr, ytr)


def to_cls(hours, margin=0.0):
    return np.array([rank[decision_from_hours(h - margin)] for h in hours])


BUDGET = 0.10   # baselines may distribute at most 10% unsafe food (kg) - about the level FoodLoop operates at


def rule_fit(h, c, q, only_sell=False, cands=140, budget=BUDGET, penalty=None):
    """Best (t_sell, t_donate) on hours_since_prepared alone, maximising SAFE recovered kg on the TRAINING split
    subject to an unsafe-share budget (or, with penalty set, net of penalised unsafe kg). This is a deliberately strong, tuned stand-in for manual rules of thumb."""
    qs = np.unique(np.concatenate([[h.min() - 1.0], np.percentile(h, np.linspace(0, 100, cands))]))
    best = (-1.0, qs[0], qs[0])
    for t1 in qs:
        for t2 in ([t1] if only_sell else qs[qs >= t1]):
            pred = np.where(h <= t1, 2, np.where(h <= t2, 1, 0))
            dist = q[pred >= 1].sum()
            unsafe = q[(pred > c) & (pred >= 1)].sum()
            if penalty is not None or dist == 0 or unsafe / dist <= budget:
                rec = q[(pred >= 1) & (pred <= c)].sum() - (penalty or 0) * unsafe
                if rec > best[0]:
                    best = (rec, t1, t2)
    return best


c_tr = dtr["decision"].map(rank).values
q_tr = dtr["quantity_kg"].values
_, t1g, t2g = rule_fit(dtr.hours_since_prepared.values, c_tr, q_tr)
_, t1s, _ = rule_fit(dtr.hours_since_prepared.values, c_tr, q_tr, only_sell=True)
rule_global = lambda d: np.where(d.hours_since_prepared <= t1g, 2, np.where(d.hours_since_prepared <= t2g, 1, 0))  # noqa: E731
_, t1r, t2r = rule_fit(dtr.hours_since_prepared.values, c_tr, q_tr, penalty=1.0)
rule_recmax = lambda d: np.where(d.hours_since_prepared <= t1r, 2, np.where(d.hours_since_prepared <= t2r, 1, 0))  # noqa: E731
rule_sellonly = lambda d: np.where(d.hours_since_prepared <= t1s, 2, 0)  # noqa: E731
cat_thr = {c: rule_fit(dtr[dtr.category == c].hours_since_prepared.values, c_tr[(dtr.category == c).values],
                       q_tr[(dtr.category == c).values], cands=90) for c in CATEGORIES}


def rule_cat(d):
    out = np.zeros(len(d), dtype=int)
    for c, (_, t1, t2) in cat_thr.items():
        m = (d.category == c).values
        h = d.hours_since_prepared.values[m]
        out[m] = np.where(h <= t1, 2, np.where(h <= t2, 1, 0))
    return out


OUT["rules"] = {"unsafe_budget_pct": BUDGET * 100,
                "global": {"sell_if_hours_le": round(float(t1g), 2), "donate_if_hours_le": round(float(t2g), 2)},
                "sell_only": {"sell_if_hours_le": round(float(t1s), 2)},
                "category": {c: {"sell_le": round(float(v[1]), 1), "donate_le": round(float(v[2]), 1)} for c, v in cat_thr.items()}}

pred_xgb = xgb.predict(Xte); pred_rf = rf.predict(Xte); pred_lr = lr.predict(Xte)
actions = {
    "Global rule": rule_global(dte), "Global rule (recovery-max)": rule_recmax(dte), "Category rule": rule_cat(dte), "Sell-only rule": rule_sellonly(dte),
    "Linear regression": to_cls(pred_lr), "Random forest": to_cls(pred_rf), "XGBoost (FoodLoop)": to_cls(pred_xgb),
}


def metrics(a, c=c_te, q=q_te):
    edible = q[c >= 1].sum()
    safe_rec = q[(a >= 1) & (a <= c)].sum()
    unsafe = q[(a > c) & (a >= 1)].sum()
    dist = q[a >= 1].sum()
    wasted_edible = q[(a == 0) & (c >= 1)].sum()
    return {"accuracy": round(float(accuracy_score(c, a) * 100), 2), "macro_f1": round(float(f1_score(c, a, average="macro")), 3),
            "unsafe_pct_of_items": round(float(((a > c) & (a >= 1)).mean() * 100), 2),
            "severe_pct_of_distributed_kg": round(float(q[(a >= 1) & (c == 0)].sum() / dist * 100), 2) if dist else 0.0,
            "unsafe_pct_of_distributed_kg": round(float(unsafe / dist * 100), 2) if dist else 0.0,
            "edible_recovered_pct": round(float(safe_rec / edible * 100), 2),
            "edible_wasted_pct": round(float(wasted_edible / edible * 100), 2)}


OUT["model_eval"] = {k: metrics(v) for k, v in actions.items()}
for k, p in (("Linear regression", pred_lr), ("Random forest", pred_rf), ("XGBoost (FoodLoop)", pred_xgb)):
    OUT["model_eval"][k]["rmse_h"] = round(float(np.sqrt(mean_squared_error(yte, p))), 2)
prev = json.load(open(ROOT / "docs" / "results.json"))["model_comparison"]["results"]
for r in prev:
    key = {"LinearRegression (baseline)": "Linear regression", "RandomForest": "Random forest", "XGBoost (deployed)": "XGBoost (FoodLoop)"}[r["model"]]
    OUT["model_eval"][key].update({"train_s": r["train_seconds"], "infer_ms": r["inference_ms_single_row"], "size_kb": r["model_size_kb"]})

# per-class precision/recall for the deployed model
cm = confusion_matrix(c_te, actions["XGBoost (FoodLoop)"], labels=[2, 1, 0])
OUT["confusion_counts"] = cm.tolist()
prec = cm.diagonal() / cm.sum(axis=0); rec = cm.diagonal() / cm.sum(axis=1)
OUT["per_class"] = {n: {"precision": round(float(p * 100), 1), "recall": round(float(r * 100), 1), "support": int(s)}
                    for n, p, r, s in zip(("sell", "donate", "compost"), prec, rec, cm.sum(axis=1))}

# ablation: retrain XGBoost with feature groups removed
groups = {"All features (full model)": [], "Without temperature": ["ambient_temp_c"],
          "Without storage type": [f"store_{s}" for s in STORAGES], "Without food category": [f"cat_{c}" for c in CATEGORIES],
          "Without quantity": ["quantity_kg"], "Hours since prepared only": [c for c in FEATURE_COLUMNS if c != "hours_since_prepared"]}
abl = {}
for name, drop in groups.items():
    cols = [c for c in FEATURE_COLUMNS if c not in drop]
    m = XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.1, n_jobs=1, tree_method="hist", random_state=1).fit(Xtr[cols], ytr)
    a = to_cls(m.predict(Xte[cols]))
    abl[name] = {**metrics(a), "rmse_h": round(float(np.sqrt(mean_squared_error(yte, m.predict(Xte[cols])))), 2)}
OUT["ablation"] = abl

# feature importance
imp = pd.Series(xgb.feature_importances_, index=FEATURE_COLUMNS)
group_imp = {"Hours since prepared": imp["hours_since_prepared"], "Ambient temperature": imp["ambient_temp_c"],
             "Quantity": imp["quantity_kg"], "Food category": imp[[f"cat_{c}" for c in CATEGORIES]].sum(),
             "Storage type": imp[[f"store_{s}" for s in STORAGES]].sum()}
group_imp = pd.Series(group_imp).sort_values()
group_imp = group_imp / group_imp.sum() * 100
OUT["feature_importance_pct"] = group_imp.round(1).to_dict()

# --- figure: confusion matrix + importance
fig, axs = plt.subplots(1, 2, figsize=(W, 2.9), gridspec_kw={"width_ratios": [1, 1.15]})
ax = axs[0]
cmn = cm / cm.sum(axis=1, keepdims=True) * 100
seq = LinearSegmentedColormap.from_list("seq", ["#eef4fc", BLUE])
ax.imshow(cmn, cmap=seq, vmin=0, vmax=100)
labs = ["Sell", "Donate", "Compost"]
ax.set_xticks(range(3)); ax.set_yticks(range(3)); ax.set_xticklabels(labs); ax.set_yticklabels(labs)
ax.set_xlabel("Predicted decision"); ax.set_ylabel("True decision")
for i in range(3):
    for j in range(3):
        ax.text(j, i, f"{cmn[i, j]:.1f}%\n({cm[i, j]})", ha="center", va="center", fontsize=8.5, color="white" if cmn[i, j] > 55 else INK)
ax.grid(False); ax.set_title("Confusion matrix (test set, n = %d)" % cm.sum()); [s.set_visible(False) for s in ax.spines.values()]
panel(ax, "(a)")
ax = axs[1]
ax.barh(group_imp.index, group_imp.values, color=BLUE, height=0.6)
for i, v in enumerate(group_imp.values):
    ax.text(v + 1, i, f"{v:.1f}%", va="center", fontsize=8.5)
ax.set_xlim(0, group_imp.max() * 1.18); ax.set_xlabel("Share of model importance (%)"); ax.grid(axis="y", visible=False)
ax.set_title("What the model relies on"); panel(ax, "(b)")
fig.tight_layout(w_pad=2.0)
save(fig, "model_cm_importance.png")

# --- figure: accuracy + safety by method
names = list(actions.keys())
fig, axs = plt.subplots(1, 2, figsize=(W, 2.7))
for ax, key, ttl, xl, tag in ((axs[0], "accuracy", "Decision accuracy", "Correct Sell / Donate / Compost decisions (%)", "(a)"),
                              (axs[1], "unsafe_pct_of_distributed_kg", "Unsafe distribution", "Distributed food past its safe window (% of kg)", "(b)")):
    vals = [OUT["model_eval"][n][key] for n in names]
    cols = [BLUE if n.startswith("XGBoost") else GRAY for n in names]
    ax.barh(names, vals, color=cols, height=0.62)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.015, i, f"{v:.1f}", va="center", fontsize=8.5)
    ax.set_xlim(0, max(vals) * 1.14); ax.invert_yaxis(); ax.set_xlabel(xl); ax.set_title(ttl); ax.grid(axis="y", visible=False)
    panel(ax, tag)
axs[1].set_yticklabels([])
fig.tight_layout(w_pad=1.4)
save(fig, "model_compare.png")

# =====================================================================================================
# 3. SAFETY MARGIN SWEEP
# =====================================================================================================
sweep = []
for m in (0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
    r = metrics(to_cls(pred_xgb, m)); r["margin_h"] = m; sweep.append(r)
OUT["margin_sweep"] = sweep
fig, ax = plt.subplots(figsize=(W * 0.62, 2.8))
ms = [s["margin_h"] for s in sweep]
ax.plot(ms, [s["edible_recovered_pct"] for s in sweep], marker="o", color=BLUE, linewidth=1.8, markersize=4.5, markeredgecolor="white")
ax.plot(ms, [s["unsafe_pct_of_distributed_kg"] for s in sweep], marker="s", color=ORANGE, linewidth=1.8, markersize=4.5, markeredgecolor="white")
ax.text(ms[-1], sweep[-1]["edible_recovered_pct"] + 11, "Edible food recovered", color=INK, ha="right", fontsize=8.5)
ax.text(ms[-1], sweep[-1]["unsafe_pct_of_distributed_kg"] + 6, "Unsafe share of distributed food", color=INK, ha="right", fontsize=8.5)
ax.set_xlabel("Safety margin added to the model's prediction (hours)"); ax.set_ylabel("Percent (%)"); ax.set_ylim(0, 100)
ax.set_title("Safety versus recovery trade-off")
fig.tight_layout()
save(fig, "margin_sweep.png")

# =====================================================================================================
# 4. BENEFIT SIMULATION: 60 vendors x 30 days, 3 NGOs, identical items under every policy
# =====================================================================================================
N_VENDORS, N_DAYS, LAMBDA, N_REPS, N_NGO = 100, 30, 2.0, 20, 3
LAT0, LAT1, LON0, LON1 = 28.52, 28.72, 77.05, 77.35
NGOS = [(28.6139, 77.2090), (28.5500, 77.1500), (28.6800, 77.2800)]
PRICE_PER_KG = {"cooked_meal": 250, "bakery": 300, "dairy": 100, "produce": 80, "packaged": 200, "dessert": 450}
FIXED_DISCOUNT = 0.5
OUT["sim_params"] = dict(vendors=N_VENDORS, days=N_DAYS, items_per_vendor_day=LAMBDA, replications=N_REPS, ngos=N_NGO,
                         fixed_discount=FIXED_DISCOUNT, price_inr_per_kg=PRICE_PER_KG, co2e_per_kg_food=CO2E_PER_KG_FOOD,
                         co2_per_km=EMISSION_KG_PER_KM, kg_per_meal=KG_PER_MEAL)

a_ml = actions["XGBoost (FoodLoop)"]
disc_ml = np.array([discount_for(h) for h in pred_xgb])
a_p1 = actions["Sell-only rule"]
a_safe = to_cls(pred_xgb, 1.0)
disc_safe = np.array([discount_for(h) for h in pred_xgb])
POLICIES = {
    "No system": np.zeros(len(dte), dtype=int),
    "Sell-only marketplace": a_p1,
    "Manual two-channel (global rule)": actions["Global rule"],
    "Manual two-channel (category rule)": actions["Category rule"],
    "FoodLoop AI": a_ml,
    "FoodLoop AI (safety-first)": a_safe,
}
price_kg = dte["category"].map(PRICE_PER_KG).values


def nn_len(depot, pts):
    p = [depot] + pts
    m = _matrix(p); cur, seen, order = 0, {0}, [0]
    while len(seen) < len(p):
        nxt = min((j for j in range(len(p)) if j not in seen), key=lambda j: m[cur][j])
        order.append(nxt); seen.add(nxt); cur = nxt
    return route_length_m(order + [0], m) / 1000


def donation_routes(rng_vendor_pos, day_vendor_pairs, method):
    """day_vendor_pairs: list of (day, vendor) for items donated. One stop per vendor-day, nearest NGO, 1 vehicle."""
    km, per = 0.0, []
    for d in sorted({d for d, _ in day_vendor_pairs}):
        vs = sorted({v for dd, v in day_vendor_pairs if dd == d})
        groups = {k: [] for k in range(N_NGO)}
        for v in vs:
            lat, lon = rng_vendor_pos[v]
            k = int(np.argmin([(lat - g[0]) ** 2 + (lon - g[1]) ** 2 for g in NGOS]))
            groups[k].append(v)
        for k, vl in groups.items():
            if not vl:
                continue
            pts = [tuple(rng_vendor_pos[v]) for v in vl]
            if method == "nn":
                r = nn_len(NGOS[k], pts); per.append((len(vl), r, None, None)); km += r
            else:
                stops = [{"id": v, "lat": p[0], "lon": p[1], "kg": 1, "name": str(v)} for v, p in zip(vl, pts)]
                pr = plan_route(NGOS[k], stops, time_limit_ms=50)
                per.append((len(vl), nn_len(NGOS[k], pts), pr["baseline_km"], pr["distance_km"])); km += pr["distance_km"]
    return km, per


t0 = time.time()
rep_rows, route_records = [], []
for rep in range(N_REPS):
    rng = np.random.default_rng(1000 + rep)
    pos = np.column_stack([rng.uniform(LAT0, LAT1, N_VENDORS), rng.uniform(LON0, LON1, N_VENDORS)])
    n = rng.poisson(LAMBDA * N_VENDORS * N_DAYS)
    item = rng.integers(0, len(dte), n); day = rng.integers(0, N_DAYS, n); ven = rng.integers(0, N_VENDORS, n)
    c, q, pk = c_te[item], q_te[item], price_kg[item]
    edible = q[c >= 1].sum()
    for name, act in POLICIES.items():
        a = act[item]
        sold_ok = (a == 2) & (c == 2)
        don_ok = (a == 1) & (c >= 1)
        rec_sell, rec_don = q[sold_ok].sum(), q[don_ok].sum()
        unsafe = q[(a > c) & (a >= 1)].sum()
        severe = q[(a >= 1) & (c == 0)].sum()
        if name.startswith("FoodLoop"):
            rev = (pk[sold_ok] * q[sold_ok] * (1 - disc_ml[item][sold_ok])).sum()
        else:
            rev = (pk[sold_ok] * q[sold_ok] * (1 - FIXED_DISCOUNT)).sum()
        km = 0.0
        d_idx = (a == 1)
        if d_idx.any() and name in ("Manual two-channel (global rule)", "Manual two-channel (category rule)"):
            km, _ = donation_routes(pos, list(zip(day[d_idx], ven[d_idx])), "nn")
        if d_idx.any() and name.startswith("FoodLoop"):
            km, per = donation_routes(pos, list(zip(day[d_idx], ven[d_idx])), "ortools")
            if name == "FoodLoop AI":
                route_records += per
        rec = rec_sell + rec_don
        rep_rows.append(dict(rep=rep, policy=name, edible_kg=edible, total_kg=q.sum(), recovered_kg=rec, sold_kg=rec_sell,
                             donated_kg=rec_don, unsafe_kg=unsafe, severe_kg=severe, wasted_kg=q.sum() - rec, revenue_inr=rev,
                             route_km=km, co2_avoided=rec * CO2E_PER_KG_FOOD, co2_transport=km * EMISSION_KG_PER_KM,
                             meals=rec / KG_PER_MEAL, donated_meals=rec_don / KG_PER_MEAL))
    print(f"rep {rep + 1}/{N_REPS} done ({time.time() - t0:.0f}s)", flush=True)

sim = pd.DataFrame(rep_rows)
sim["co2_net"] = sim.co2_avoided - sim.co2_transport
sim["recovered_pct_of_edible"] = sim.recovered_kg / sim.edible_kg * 100
sim["unsafe_pct_of_distributed"] = sim.unsafe_kg / (sim.recovered_kg + sim.unsafe_kg).replace(0, np.nan) * 100
sim["severe_pct_of_distributed"] = sim.severe_kg / (sim.recovered_kg + sim.unsafe_kg).replace(0, np.nan) * 100
sim["kg_per_route_km"] = sim.donated_kg / sim.route_km.replace(0, np.nan)
sim["co2_transport_per_kg_donated"] = sim.co2_transport / sim.donated_kg.replace(0, np.nan)


def summ(col, scale=1.0):
    g = sim.groupby("policy")[col]
    return {p: {"mean": round(float(g.get_group(p).mean() * scale), 2),
                "ci95": round(float(1.96 * g.get_group(p).std(ddof=1) / np.sqrt(N_REPS) * scale), 2)} for p in POLICIES}


OUT["sim"] = {
    "recovered_pct_of_edible": summ("recovered_pct_of_edible"), "recovered_kg_per_day": summ("recovered_kg", 1 / N_DAYS),
    "meals_per_day": summ("meals", 1 / N_DAYS), "donated_meals_per_day": summ("donated_meals", 1 / N_DAYS),
    "co2_avoided_per_day": summ("co2_avoided", 1 / N_DAYS), "co2_net_per_day": summ("co2_net", 1 / N_DAYS),
    "route_km_per_day": summ("route_km", 1 / N_DAYS), "revenue_per_day": summ("revenue_inr", 1 / N_DAYS),
    "unsafe_pct": summ("unsafe_pct_of_distributed"), "severe_pct": summ("severe_pct_of_distributed"),
    "kg_per_route_km": summ("kg_per_route_km"), "transport_co2_per_kg_donated": summ("co2_transport_per_kg_donated"),
    "recovered_kg_per_vendor_day": summ("recovered_kg", 1 / N_DAYS / N_VENDORS), "meals_per_vendor_day": summ("meals", 1 / N_DAYS / N_VENDORS),
    "revenue_per_vendor_day": summ("revenue_inr", 1 / N_DAYS / N_VENDORS), "co2_net_per_vendor_day": summ("co2_net", 1 / N_DAYS / N_VENDORS), "wasted_kg_per_day": summ("wasted_kg", 1 / N_DAYS),
    "total_kg_per_day": {"mean": round(float(sim.total_kg.mean() / N_DAYS), 1)},
    "edible_kg_per_day": {"mean": round(float(sim.edible_kg.mean() / N_DAYS), 1)},
}
base_best = max((p for p in POLICIES if not p.startswith("FoodLoop") and p != "No system"), key=lambda p: sim[sim.policy == p].recovered_kg.mean())
fl, bb = sim[sim.policy == "FoodLoop AI"], sim[sim.policy == base_best]
OUT["sim"]["best_baseline"] = base_best
OUT["sim"]["breakeven_uptake_pct"] = round(float(bb.recovered_kg.mean() / fl.recovered_kg.mean() * 100), 1)
OUT["sim"]["relative_gain_vs_best_baseline_pct"] = {
    "recovered_kg": round(float((fl.recovered_kg.mean() / bb.recovered_kg.mean() - 1) * 100), 1),
    "co2_net": round(float((fl.co2_net.mean() / bb.co2_net.mean() - 1) * 100), 1),
    "revenue": round(float((fl.revenue_inr.mean() / bb.revenue_inr.mean() - 1) * 100), 1)}
OUT["sim"]["per_year_extrapolation_FoodLoop_vs_none"] = {
    "kg": round(float(fl.recovered_kg.mean() / N_DAYS * 365), 0), "meals": round(float(fl.meals.mean() / N_DAYS * 365), 0),
    "co2_net_kg": round(float(fl.co2_net.mean() / N_DAYS * 365), 0)}

# routing stats from the FoodLoop donation routes
rr = pd.DataFrame(route_records, columns=["stops", "nn_km", "acc_km", "ort_km"]).dropna()
rr = rr[rr.stops >= 2]
OUT["routing_sim"] = {
    "n_routes": int(len(rr)), "mean_stops": round(float(rr.stops.mean()), 1),
    "mean_acceptance_km": round(float(rr.acc_km.mean()), 1), "mean_nn_km": round(float(rr.nn_km.mean()), 1), "mean_ortools_km": round(float(rr.ort_km.mean()), 1),
    "saved_vs_acceptance_pct": round(float((1 - rr.ort_km.sum() / rr.acc_km.sum()) * 100), 1),
    "saved_vs_nn_pct": round(float((1 - rr.ort_km.sum() / rr.nn_km.sum()) * 100), 1),
    "ortools_worse_than_nn_pct_of_routes": round(float((rr.ort_km > rr.nn_km + 1e-6).mean() * 100), 1),
}
bins = [(2, 4), (5, 7), (8, 10), (11, 30)]
OUT["routing_by_stops"] = []
for lo, hi in bins:
    s = rr[(rr.stops >= lo) & (rr.stops <= hi)]
    if len(s):
        OUT["routing_by_stops"].append({"stops": f"{lo}-{hi}" if hi < 30 else f"{lo}+", "routes": int(len(s)), "acceptance_km": round(float(s.acc_km.mean()), 1),
                                        "nn_km": round(float(s.nn_km.mean()), 1), "ortools_km": round(float(s.ort_km.mean()), 1),
                                        "saved_vs_nn_pct": round(float((1 - s.ort_km.sum() / s.nn_km.sum()) * 100), 1)})

# --- figure: benefits (2x2)
short = {"No system": "No system", "Sell-only marketplace": "Sell-only marketplace", "Manual two-channel (global rule)": "Manual, global rule",
         "Manual two-channel (category rule)": "Manual, category rule", "FoodLoop AI": "FoodLoop AI", "FoodLoop AI (safety-first)": "FoodLoop AI (safety-first)"}
fig, axs = plt.subplots(2, 2, figsize=(W, 6.3))
for ax, key, ttl, yl, tag, fmt in ((axs[0, 0], "recovered_pct_of_edible", "Edible surplus recovered", "% of edible food (kg)", "(a)", "{:.1f}"),
                                   (axs[0, 1], "meals_per_vendor_day", "Meals provided per vendor per day", "Meals / vendor / day", "(b)", "{:.1f}"),
                                   (axs[1, 0], "co2_net_per_vendor_day", "Net emissions avoided", "kg CO$_2$e / vendor / day", "(c)", "{:.1f}"),
                                   (axs[1, 1], "revenue_per_vendor_day", "Vendor revenue recovered", "INR / vendor / day", "(d)", "{:,.0f}")):
    d = OUT["sim"][key]
    vals = [d[p]["mean"] for p in POLICIES]; err = [d[p]["ci95"] for p in POLICIES]
    cols = [BLUE if p == "FoodLoop AI" else ("#7fb0ec" if p.startswith("FoodLoop") else GRAY) for p in POLICIES]
    ax.bar(range(len(vals)), vals, yerr=err, color=cols, width=0.62, capsize=2.5, error_kw={"elinewidth": 0.9, "ecolor": INK})
    top = max(v + e for v, e in zip(vals, err))
    for i, v in enumerate(vals):
        ax.text(i, v + err[i] + top * 0.02, fmt.format(v), ha="center", va="bottom", fontsize=8.5)
    ax.set_xticks(range(len(vals))); ax.set_xticklabels([short[p] for p in POLICIES], fontsize=7.4, rotation=32, ha="right", rotation_mode="anchor")
    ax.set_ylabel(yl); ax.set_title(ttl); ax.set_ylim(0, top * 1.14); ax.grid(axis="x", visible=False); panel(ax, tag)
fig.tight_layout(h_pad=1.5, w_pad=1.4)
save(fig, "benefits.png")

# --- figure: uptake sensitivity
fig, ax = plt.subplots(figsize=(W * 0.66, 2.9))
u = np.linspace(0.4, 1.0, 7)
flm = OUT["sim"]["recovered_kg_per_day"]["FoodLoop AI"]["mean"]
ax.plot(u * 100, u * flm, color=BLUE, linewidth=2, marker="o", markersize=4.5, markeredgecolor="white")
for p, col, ls in (("Manual two-channel (global rule)", GRAY, "--"), ("Manual two-channel (category rule)", GRAY, ":"), ("Sell-only marketplace", GRAY, "-.")):
    v = OUT["sim"]["recovered_kg_per_day"][p]["mean"]
    ax.axhline(v, color=col, linestyle=ls, linewidth=1.3)
    ax.text(40.5, v + flm * 0.015, short[p].replace("\n", " ") + " at 100% uptake", fontsize=8, color=MUTED, va="bottom")
ax.text(99, flm * 0.985, "FoodLoop AI", color=BLUE, ha="right", va="top", fontsize=9, fontweight="bold")
ax.set_xlabel("Share of FoodLoop listings actually claimed (%)"); ax.set_ylabel("Food recovered (kg / day)")
ax.set_title("How much uptake does FoodLoop need to win?"); ax.set_xlim(40, 100); ax.set_ylim(0, flm * 1.08)
fig.tight_layout()
save(fig, "uptake.png")

# --- figure: routing
fig, axs = plt.subplots(1, 2, figsize=(W, 2.8))
ax = axs[0]
bp = ax.boxplot([rr.acc_km, rr.nn_km, rr.ort_km], tick_labels=["Acceptance\norder", "Nearest\nneighbour", "OR-Tools\n(FoodLoop)"], patch_artist=True,
                showfliers=False, widths=0.55, medianprops={"color": INK, "linewidth": 1.4})
for patch, col in zip(bp["boxes"], (GRAY, GRAY, BLUE)):
    patch.set_facecolor(col); patch.set_alpha(0.9); patch.set_edgecolor("white")
ax.set_ylabel("Route length (km)"); ax.set_title("Daily NGO pickup routes"); ax.grid(axis="x", visible=False); panel(ax, "(a)")
ax = axs[1]
bs = OUT["routing_by_stops"]
ax.bar([b["stops"] for b in bs], [b["saved_vs_nn_pct"] for b in bs], color=BLUE, width=0.6)
for i, b in enumerate(bs):
    ax.text(i, b["saved_vs_nn_pct"] + 0.25, f"{b['saved_vs_nn_pct']:.1f}%", ha="center", fontsize=8.5)
ax.set_xlabel("Stops on the route"); ax.set_ylabel("Shorter than nearest neighbour (%)"); ax.set_title("Savings grow with route size")
ax.set_ylim(0, max(b["saved_vs_nn_pct"] for b in bs) * 1.25); ax.grid(axis="x", visible=False); panel(ax, "(b)")
fig.tight_layout(w_pad=1.6)
save(fig, "routing.png")

json.dump(OUT, open(ROOT / "docs" / "paper_results.json", "w"), indent=2, default=float)
print("saved; total time %.0fs" % (time.time() - t0))
