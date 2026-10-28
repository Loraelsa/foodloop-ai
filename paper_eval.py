"""All numbers and charts for the paper's EDA, accuracy and benefit sections.

Run from the repo root:  python scripts/paper_eval.py [--margin 0.5] [--runs 40]
Writes docs/paper/results_paper.json and docs/paper/figs/*.png (300 dpi).

Honest scope: the dataset is the synthetic FoodLoop surplus-food dataset produced by
backend/app/ml/features.py (rule-based shelf life + noise). The 'true remaining hours' used as ground
truth is that generator's output, so results show the pipeline works and how components compare
under the stated assumptions; they are not field measurements.
"""
import argparse, io, json, sys, time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (confusion_matrix, mean_absolute_error, mean_squared_error, precision_recall_fscore_support, r2_score)
from sklearn.model_selection import KFold, train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.compose import TransformedTargetRegressor
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.config import CO2E_PER_KG_FOOD, EMISSION_KG_PER_KM, KG_PER_MEAL, ROAD_FACTOR  # noqa: E402
from app.ml.engine import discount_for  # noqa: E402
from app.ml.features import (BASE_SHELF_HOURS, CATEGORIES, DONATE_MIN_HOURS, FEATURE_COLUMNS, SELL_MIN_HOURS,  # noqa: E402
                             STORAGE_MULT, STORAGES, decision_from_hours, featurize, generate_dataset)
from app.routing import _matrix, haversine_km, plan_route, route_length_m  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--margin", type=float, default=0.5)
ap.add_argument("--runs", type=int, default=40)
ap.add_argument("--no-sim", action="store_true")
args = ap.parse_args()
MARGIN = args.margin
OUT = ROOT / "docs" / "paper"
FIGS = OUT / "figs"
FIGS.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------------- plotting setup
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

INK, MUTED, GRID = "#1b1b1b", "#52514e", "#dcdcd8"
C_BLUE, C_ORANGE, C_AQUA, C_GREY = "#2a78d6", "#eb6834", "#1baf7a", "#8c8c88"  # validated slots 1-3 + neutral
DEC_COL = {"sell": C_BLUE, "donate": C_ORANGE, "compost": C_AQUA}
STRAT_COL = {"A": C_GREY, "B": C_ORANGE, "C": C_AQUA, "D": C_BLUE}
plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": 9, "axes.titlesize": 9.5,
    "axes.labelsize": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.dpi": 100, "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
})
SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f8fd", C_BLUE])
DIV = LinearSegmentedColormap.from_list("div", [C_ORANGE, "#efefec", C_BLUE])


def save(fig, name):
    fig.savefig(FIGS / f"{name}.png")
    plt.close(fig)


def panel(ax, tag):
    ax.text(-0.02, 1.08, tag, transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="right")


R = {"meta": {"margin_hours": MARGIN, "co2e_per_kg_food": CO2E_PER_KG_FOOD, "emission_kg_per_km": EMISSION_KG_PER_KM,
              "kg_per_meal": KG_PER_MEAL, "road_factor": ROAD_FACTOR, "sell_min_h": SELL_MIN_HOURS,
              "donate_min_h": DONATE_MIN_HOURS}}

# ----------------------------------------------------------------------------------- dataset + EDA
N = 20000
df = generate_dataset(N, seed=7)
df["total_life_h"] = df["remaining_hours"] + df["hours_since_prepared"]
R["dataset"] = {
    "n": N,
    "numeric": {c: {k: round(float(v), 2) for k, v in df[c].describe()[["mean", "std", "min", "50%", "max"]].items()}
                for c in ["hours_since_prepared", "ambient_temp_c", "quantity_kg", "remaining_hours"]},
    "category_counts": df.category.value_counts().to_dict(),
    "storage_counts": df.storage.value_counts().to_dict(),
    "decision_counts": df.decision.value_counts().to_dict(),
    "decision_share_pct": (df.decision.value_counts(normalize=True) * 100).round(1).to_dict(),
    "total_kg": round(float(df.quantity_kg.sum()), 1),
    "kg_by_decision": df.groupby("decision").quantity_kg.sum().round(1).to_dict(),
}
share_cat = pd.crosstab(df.category, df.decision, normalize="index").reindex(CATEGORIES)[["sell", "donate", "compost"]] * 100
R["dataset"]["decision_share_by_category_pct"] = share_cat.round(1).to_dict(orient="index")
sell_ct = (df.assign(is_sell=df.decision == "sell").pivot_table(index="category", columns="storage", values="is_sell", aggfunc="mean")
           .reindex(index=CATEGORIES, columns=STORAGES) * 100)
R["dataset"]["sell_share_cat_storage_pct"] = sell_ct.round(1).to_dict(orient="index")

NICE_CAT = {"cooked_meal": "Cooked meal", "bakery": "Bakery", "dairy": "Dairy", "produce": "Fruit & veg",
            "packaged": "Packaged", "dessert": "Dessert"}
NICE_ST = {"ambient": "Room temp.", "refrigerated": "Refrigerated", "hot_held": "Kept hot"}

# --- EDA figure 1: remaining-life distribution + decision mix by category
fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.7), gridspec_kw={"width_ratios": [1, 1.05]})
rem = df.remaining_hours.clip(-10, 60)
a.hist(rem, bins=np.arange(-10, 61, 2), color=C_GREY, edgecolor="white", linewidth=0.4)
a.axvline(DONATE_MIN_HOURS, color=C_AQUA, lw=1.4); a.axvline(SELL_MIN_HOURS, color=C_ORANGE, lw=1.4)
ymax = a.get_ylim()[1]
a.text(-9, ymax * 0.93, "compost\n(<1 h)", color=C_AQUA, fontsize=8, va="top", fontweight="bold")
a.text(1.6, ymax * 0.62, "donate\n(1–4 h)", color=C_ORANGE, fontsize=8, va="top", fontweight="bold")
a.text(14, ymax * 0.93, "sell (≥4 h)", color=C_BLUE, fontsize=8, va="top", fontweight="bold")
a.set_xlabel("Remaining safe life (h), clipped to [−10, 60]"); a.set_ylabel("Lots"); panel(a, "(a)")
order = share_cat.sort_values("sell").index
left = np.zeros(len(order))
for d in ["sell", "donate", "compost"]:
    vals = share_cat.loc[order, d].values
    b.barh([NICE_CAT[o] for o in order], vals, left=left, color=DEC_COL[d], edgecolor="white", linewidth=1.2, label=d.capitalize(), height=0.7)
    for i, (v, l0) in enumerate(zip(vals, left)):
        if v >= 9:
            b.text(l0 + v / 2, i, f"{v:.0f}", ha="center", va="center", color="white", fontsize=7.5, fontweight="bold")
    left += vals
b.set_xlim(0, 100); b.set_xlabel("Share of lots (%)"); b.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.45, 1.0), frameon=False, handlelength=1.0)
b.grid(axis="y", visible=False); panel(b, "(b)")
fig.tight_layout(w_pad=1.5); save(fig, "eda1_distribution_mix")

# --- EDA figure 2: sell share by category x storage + temperature effect on effective life
fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.8), gridspec_kw={"width_ratios": [1, 1.1]})
im = a.imshow(sell_ct.values, cmap=SEQ, vmin=0, vmax=100, aspect="auto")
a.set_xticks(range(3)); a.set_xticklabels([NICE_ST[s] for s in STORAGES]); a.set_yticks(range(6)); a.set_yticklabels([NICE_CAT[c] for c in CATEGORIES])
a.grid(False)
for i in range(6):
    for j in range(3):
        v = sell_ct.values[i, j]
        a.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8, color="white" if v > 55 else INK)
a.set_title("Lots routed to “sell” (%)", fontsize=9, loc="left"); panel(a, "(a)")
for s in a.spines.values(): s.set_visible(False)
df["temp_bin"] = pd.cut(df.ambient_temp_c, bins=np.arange(10, 50, 5), right=False)
tl = df.groupby(["storage", "temp_bin"], observed=True).apply(lambda g: (g.total_life_h / g.category.map(BASE_SHELF_HOURS)).mean()).unstack(0)
xs = [iv.left + 2.5 for iv in tl.index]
for s, col in zip(["refrigerated", "hot_held", "ambient"], [C_BLUE, C_ORANGE, C_AQUA]):
    b.plot(xs, tl[s].values, color=col, lw=2, marker="o", ms=4.5, label=NICE_ST[s])
    b.text(xs[-1] + 0.8, tl[s].values[-1], NICE_ST[s], color=col, fontsize=8, va="center", fontweight="bold")
b.set_xlim(11, 52); b.set_xlabel("Ambient temperature (°C)"); b.set_ylabel("Effective life ÷ 25 °C label life"); panel(b, "(b)")
R["dataset"]["temp_effect"] = {s: [round(float(v), 2) for v in tl[s].values] for s in tl.columns}; R["dataset"]["temp_bins_mid"] = xs
fig.tight_layout(w_pad=1.5); save(fig, "eda2_storage_temperature")

# ----------------------------------------------------------------------------------- models
X = featurize(df); y = df["remaining_hours"]
Xtr, Xte, ytr, yte, dtr, dte = train_test_split(X, y, df["decision"], test_size=0.2, random_state=42)
LABELS = ["sell", "donate", "compost"]


def dec_vec(h, margin=0.0):
    h = np.asarray(h) - margin
    return np.where(h >= SELL_MIN_HOURS, "sell", np.where(h >= DONATE_MIN_HOURS, "donate", "compost"))


def timed_fit(model):
    t0 = time.process_time(); model.fit(Xtr, ytr); return time.process_time() - t0


def single_ms(model, reps=200):
    row = Xte.iloc[[0]]; model.predict(row)
    t0 = time.perf_counter()
    for _ in range(reps): model.predict(row)
    return (time.perf_counter() - t0) / reps * 1000


def size_kb(model):
    buf = io.BytesIO(); joblib.dump(model, buf); return buf.tell() / 1024


deployed = XGBRegressor(); deployed.load_model(str(ROOT / "backend/app/ml/artifacts/freshness_xgb.json"))
models = {
    "Linear regression": LinearRegression(),
    "Neural network (MLP 64-64)": TransformedTargetRegressor(regressor=make_pipeline(StandardScaler(), MLPRegressor((64, 64), max_iter=300, early_stopping=True, random_state=1)), transformer=StandardScaler()),
    "Random forest": RandomForestRegressor(n_estimators=120, max_depth=12, n_jobs=1, random_state=1),
    "XGBoost (deployed)": XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.1, n_jobs=1, tree_method="hist", random_state=1),
}
rows, fitted = [], {}
for name, m in models.items():
    cpu = timed_fit(m); fitted[name] = m
    p = m.predict(Xte); dp = dec_vec(p, 0.0)
    pr, rc, f1, _ = precision_recall_fscore_support(dte, dp, labels=LABELS, average="macro", zero_division=0)
    rows.append(dict(model=name, rmse_h=float(np.sqrt(mean_squared_error(yte, p))), mae_h=float(mean_absolute_error(yte, p)), r2=float(r2_score(yte, p)),
                     accuracy=float((dp == dte.values).mean()), macro_f1=float(f1), train_cpu_s=cpu, infer_ms=single_ms(m), size_kb=size_kb(m)))
    print(rows[-1])
# 5-fold CV decision accuracy
kf = KFold(5, shuffle=True, random_state=0)
cv = {}
for name, m in models.items():
    import copy
    accs = []
    for tr, te in kf.split(X):
        mm = copy.deepcopy(m); mm.fit(X.iloc[tr], y.iloc[tr])
        accs.append(float((dec_vec(mm.predict(X.iloc[te])) == df["decision"].iloc[te].values).mean()))
    cv[name] = (float(np.mean(accs)), float(np.std(accs)))
for r in rows: r["cv_acc_mean"], r["cv_acc_std"] = cv[r["model"]]
R["models"] = rows

# ---- deployed-model decision quality (the model actually shipped in the app) at the chosen margin
pred_te = deployed.predict(Xte)
true_rem_te = yte.values
dp0, dpm = dec_vec(pred_te, 0.0), dec_vec(pred_te, MARGIN)
cm = confusion_matrix(dte, dpm, labels=LABELS)
pr, rc, f1, sup = precision_recall_fscore_support(dte, dpm, labels=LABELS, zero_division=0)
R["deployed"] = {"accuracy_margin0": float((dp0 == dte.values).mean()), "accuracy": float((dpm == dte.values).mean()),
                 "confusion": cm.tolist(), "per_class": {l: dict(precision=float(pr[i]), recall=float(rc[i]), f1=float(f1[i]), support=int(sup[i])) for i, l in enumerate(LABELS)},
                 "rmse_h": float(np.sqrt(mean_squared_error(yte, pred_te))), "r2": float(r2_score(yte, pred_te)), "n_test": int(len(yte))}


def release_metrics(release_mask, truth_rem, kg=None):
    """release_mask: lot is sold/donated.  Unsafe = released although true remaining < donate minimum."""
    rel = np.asarray(release_mask, bool); t = np.asarray(truth_rem)
    safe_lot = t >= DONATE_MIN_HOURS
    n_rel = max(rel.sum(), 1)
    return {"released_pct": float(rel.mean() * 100),
            "unsafe_release_pct_of_released": float((rel & ~safe_lot).sum() / n_rel * 100),
            "severe_unsafe_pct_of_released": float((rel & (t <= 0)).sum() / n_rel * 100),
            "needless_discard_pct_of_safe": float((~rel & safe_lot).sum() / max(safe_lot.sum(), 1) * 100),
            "release_accuracy_pct": float((rel == safe_lot).mean() * 100)}


# safety-margin sweep
sweep = []
for mg in [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]:
    d = dec_vec(pred_te, mg); m_ = release_metrics(d != "compost", true_rem_te)
    m_.update(margin=mg, three_class_acc=float((d == dte.values).mean() * 100)); sweep.append(m_)
R["margin_sweep"] = sweep

# manual baselines on the same test lots
te_df = df.loc[Xte.index]
r1 = (te_df.hours_since_prepared <= 4).values                                    # fixed 4-hour rule of thumb
r2 = (te_df.hours_since_prepared < te_df.category.map(BASE_SHELF_HOURS)).values  # static label life, ignores storage + temperature
R["decision_quality"] = {"4-hour rule": release_metrics(r1, true_rem_te), "Static label life": release_metrics(r2, true_rem_te),
                         "FoodLoop model": release_metrics(dpm != "compost", true_rem_te)}

# robustness: hotter climate + more noise (unseen at training time)
def gen_shift(n, seed, temp_mean=35.0, temp_sd=4.0, noise=0.12):
    rng = np.random.default_rng(seed)
    cat = rng.choice(CATEGORIES, n); st = rng.choice(STORAGES, n, p=[0.55, 0.30, 0.15])
    temp = np.clip(rng.normal(temp_mean, temp_sd, n), 12, 46)
    base = np.array([BASE_SHELF_HOURS[c] * STORAGE_MULT[s] for c, s in zip(cat, st)])
    since = rng.uniform(0, 1.3, n) * base * 2 ** ((25 - temp) / 10); qty = np.round(rng.gamma(2.0, 3.0, n) + 0.5, 1)
    life = base * 2 ** ((25 - temp) / 10)
    rem = life - since + rng.normal(0, noise, n) * np.abs(base) + rng.normal(0, 0.4, n)
    return pd.DataFrame(dict(category=cat, storage=st, ambient_temp_c=temp, hours_since_prepared=since, quantity_kg=qty, remaining_hours=rem))

rob = {}
for label, kw in [("In-distribution (mean 29 °C)", None), ("Hot season (mean 35 °C)", dict(temp_mean=35, temp_sd=4, noise=0.06)),
                  ("Hot season + double noise", dict(temp_mean=35, temp_sd=4, noise=0.12))]:
    if kw is None:
        d = te_df.copy(); p = pred_te
    else:
        d = gen_shift(5000, 99, **kw); p = deployed.predict(featurize(d))
    truth = d.remaining_hours.values; dd = dec_vec(p, MARGIN); td = dec_vec(truth)
    rm = release_metrics(dd != "compost", truth)
    r2m = release_metrics((d.hours_since_prepared < d.category.map(BASE_SHELF_HOURS)).values, truth)
    rob[label] = {"three_class_acc": float((dd == td).mean() * 100), "unsafe_release_pct": rm["unsafe_release_pct_of_released"],
                  "needless_discard_pct": rm["needless_discard_pct_of_safe"], "rule_unsafe_release_pct": r2m["unsafe_release_pct_of_released"]}
R["robustness"] = rob

# --- feature importance + correlation (EDA figure 3)
imp = pd.Series(deployed.get_booster().get_score(importance_type="gain"))
imp.index = [FEATURE_COLUMNS[int(i[1:])] if i.startswith("f") and i[1:].isdigit() else i for i in imp.index]
imp = (imp / imp.sum() * 100).sort_values(ascending=False)
grp = {"hours_since_prepared": "Hours since prepared", "ambient_temp_c": "Ambient temperature", "quantity_kg": "Quantity"}
agg = {}
for k, v in imp.items():
    agg[grp.get(k, NICE_CAT.get(k[4:], None) and "Category" if k.startswith("cat_") else "Storage" if k.startswith("store_") else k)] = agg.get(grp.get(k, "Category" if k.startswith("cat_") else "Storage"), 0) + v
agg2 = {}
for k, v in imp.items():
    name = grp.get(k) or ("Food category" if k.startswith("cat_") else "Storage type")
    agg2[name] = agg2.get(name, 0) + v
agg2 = pd.Series(agg2).sort_values()
R["feature_importance_pct"] = {k: round(float(v), 1) for k, v in agg2.sort_values(ascending=False).items()}
corr = df[["hours_since_prepared", "ambient_temp_c", "quantity_kg", "remaining_hours"]].corr(method="spearman")
R["spearman"] = corr.round(2).to_dict()
fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.7), gridspec_kw={"width_ratios": [1, 1]})
lab = ["Hours since\nprepared", "Ambient\ntemp.", "Quantity", "Remaining\nlife"]
a.imshow(corr.values, cmap=DIV, vmin=-1, vmax=1); a.grid(False)
a.set_xticks(range(4)); a.set_xticklabels(lab, fontsize=7.5); a.set_yticks(range(4)); a.set_yticklabels(lab, fontsize=7.5)
for i in range(4):
    for j in range(4):
        v = corr.values[i, j]; a.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8, color="white" if abs(v) > 0.6 else INK)
for s in a.spines.values(): s.set_visible(False)
a.set_title("Spearman correlation", fontsize=9, loc="left"); panel(a, "(a)")
b.barh(agg2.index, agg2.values, color=C_BLUE, height=0.62)
for i, v in enumerate(agg2.values): b.text(v + 1, i, f"{v:.0f}%", va="center", fontsize=8)
b.set_xlim(0, max(agg2.values) * 1.18); b.set_xlabel("Share of model gain (%)"); b.grid(axis="y", visible=False); panel(b, "(b)")
fig.tight_layout(w_pad=1.5); save(fig, "eda3_correlation_importance")

# --- accuracy figure: confusion matrix + safety-margin trade-off
fig, (a, b) = plt.subplots(1, 2, figsize=(6.5, 2.8), gridspec_kw={"width_ratios": [1, 1.1]})
cmn = cm / cm.sum(axis=1, keepdims=True) * 100
a.imshow(cmn, cmap=SEQ, vmin=0, vmax=100); a.grid(False)
a.set_xticks(range(3)); a.set_xticklabels([l.capitalize() for l in LABELS]); a.set_yticks(range(3)); a.set_yticklabels([l.capitalize() for l in LABELS])
a.set_xlabel("Predicted"); a.set_ylabel("Actual")
for i in range(3):
    for j in range(3):
        a.text(j, i, f"{cmn[i, j]:.1f}%\n(n={cm[i, j]})", ha="center", va="center", fontsize=7.8, color="white" if cmn[i, j] > 55 else INK)
for s in a.spines.values(): s.set_visible(False)
panel(a, "(a)")
mg = [s["margin"] for s in sweep]
b.plot(mg, [s["unsafe_release_pct_of_released"] for s in sweep], color=C_ORANGE, lw=2, marker="o", ms=4.5)
b.plot(mg, [s["needless_discard_pct_of_safe"] for s in sweep], color=C_BLUE, lw=2, marker="o", ms=4.5)
b.text(mg[-1] + 0.05, sweep[-1]["unsafe_release_pct_of_released"] + 0.25, "Unsafe releases\n(% of released)", color=C_ORANGE, fontsize=8, ha="right", va="bottom", fontweight="bold")
b.text(mg[-1] + 0.05, sweep[-1]["needless_discard_pct_of_safe"] - 0.3, "Safe food discarded\n(% of safe lots)", color=C_BLUE, fontsize=8, ha="right", va="top", fontweight="bold")
b.axvline(MARGIN, color=C_GREY, lw=1, ls="--"); b.text(MARGIN + 0.04, b.get_ylim()[1] * 0.97, "deployed", color=MUTED, fontsize=8, va="top")
b.set_xlabel("Safety margin subtracted from prediction (h)"); b.set_ylabel("%"); panel(b, "(b)")
fig.tight_layout(w_pad=1.5); save(fig, "accuracy_confusion_margin")

# --- model comparison figure (no dual axis: three small panels)
fig, axs = plt.subplots(1, 3, figsize=(6.5, 2.3))
names = ["Linear\nregression", "Neural\nnet (MLP)", "Random\nforest", "XGBoost\n(deployed)"]
cols = [C_GREY, C_GREY, C_GREY, C_BLUE]
for ax, key, ttl, fmt in [(axs[0], "accuracy", "Decision accuracy (%)", "{:.1f}"), (axs[1], "infer_ms", "Inference (ms/row)", "{:.1f}"), (axs[2], "train_cpu_s", "Training CPU time (s)", "{:.1f}")]:
    vals = [r[key] * (100 if key == "accuracy" else 1) for r in rows]
    ax.bar(range(4), vals, color=cols, width=0.68); ax.set_xticks(range(4)); ax.set_xticklabels(names, fontsize=7); ax.set_title(ttl, fontsize=8.8, loc="left")
    ax.grid(axis="x", visible=False)
    for i, v in enumerate(vals): ax.text(i, v + max(vals) * 0.02, fmt.format(v), ha="center", fontsize=7.8)
    ax.set_ylim(0, max(vals) * 1.15)
fig.tight_layout(w_pad=1.2); save(fig, "model_comparison")

# ----------------------------------------------------------------------------------- scenario simulation
if args.no_sim:
    (OUT / "results_paper.json").write_text(json.dumps(R, indent=2)); sys.exit()

PPK = {"cooked_meal": 150, "bakery": 120, "dairy": 90, "produce": 60, "packaged": 200, "dessert": 250}  # INR/kg, assumed
NGO = [(28.6139, 77.2090), (28.5700, 77.2400), (28.6600, 77.1500)]
BBOX = (28.50, 28.72, 77.10, 77.32)
pool = generate_dataset(60000, seed=123)
pool["pred"] = deployed.predict(featurize(pool))
pool["pred_adj"] = pool.pred - MARGIN
pool["dec"] = dec_vec(pool.pred_adj.values)
pool["r2"] = (pool.hours_since_prepared < pool.category.map(BASE_SHELF_HOURS)).values
pool["mrp"] = pool.quantity_kg * pool.category.map(PPK)
pool["disc"] = [discount_for(h) for h in pool.pred_adj.clip(lower=0)]
pool["safe"] = pool.remaining_hours >= DONATE_MIN_HOURS
P = {k: pool[k].values for k in ["quantity_kg", "remaining_hours", "dec", "r2", "mrp", "disc", "safe"]}


def nn_len(m):
    n = len(m); cur, seen, order = 0, {0}, [0]
    while len(seen) < n:
        nxt = min((j for j in range(n) if j not in seen), key=lambda j: m[cur][j]); order.append(nxt); seen.add(nxt); cur = nxt
    return route_length_m(order + [0], m) / 1000


def routes_km(lots_mask, idx, day, vend, vngo, vpos, optimiser):
    """Sum route km for the collected lots, one route per NGO per day."""
    tot_opt = tot_nn = tot_acc = 0.0; trips = 0
    for g in np.unique(day[lots_mask] * 10 + vngo[vend[lots_mask]]):
        d, n = divmod(int(g), 10)
        sel = lots_mask & (day == d) & (vngo[vend] == n)
        vs = list(dict.fromkeys(vend[sel]))
        stops = [{"id": int(v), "lat": vpos[v][0], "lon": vpos[v][1], "kg": 1.0, "name": str(v)} for v in vs]
        pts = [NGO[n]] + [(s["lat"], s["lon"]) for s in stops]
        m = _matrix(pts)
        tot_nn += nn_len(m); tot_acc += route_length_m(list(range(len(pts))) + [0], m) / 1000; trips += 1
        if optimiser:
            tot_opt += plan_route(NGO[n], stops, 1, None, 30)["distance_km"]
    return tot_opt, tot_nn, tot_acc, trips


def run(seed, u_sell=0.6, u_coll=0.85, days=30, V=40, lam=1.2, optimise=True):
    rng = np.random.default_rng(seed)
    vpos = np.c_[rng.uniform(BBOX[0], BBOX[1], V), rng.uniform(BBOX[2], BBOX[3], V)]
    vngo = np.array([int(np.argmin([haversine_km(*vp, *n) for n in NGO])) for vp in vpos])
    cnt = rng.poisson(lam, (days, V)); day = np.repeat(np.repeat(np.arange(days), V), cnt.ravel()); vend = np.repeat(np.tile(np.arange(V), days), cnt.ravel())
    idx = rng.integers(0, len(pool), len(day)); kg = P["quantity_kg"][idx]; tr = P["remaining_hours"][idx]; safe = P["safe"][idx]
    mrp = P["mrp"][idx]; dec = P["dec"][idx]; r2 = P["r2"][idx]; disc = P["disc"][idx]
    u1, u2 = rng.random(len(day)), rng.random(len(day))
    total = kg.sum(); out = {}

    def tally(name, sold, coll, revenue, opt_km=0.0, nn_km=0.0, acc_km=0.0, trips=0, composted=0.0, km_used="nn"):
        to_people = (sold | coll); safe_kg = kg[to_people & safe].sum(); unsafe_kg = kg[to_people & ~safe].sum()
        km = {"opt": opt_km, "nn": nn_km, "acc": acc_km}[km_used]
        out[name] = dict(total_kg=total, safe_diverted_kg=safe_kg, unsafe_kg=unsafe_kg, wasted_kg=total - kg[to_people].sum(), composted_kg=composted,
                         diversion_pct=safe_kg / total * 100, sold_kg=kg[sold].sum(), donated_kg=kg[coll].sum(), revenue_inr=revenue, meals=safe_kg / KG_PER_MEAL,
                         ngo_km=km, ngo_trips=trips, co2_food_avoided=safe_kg * CO2E_PER_KG_FOOD, co2_transport=km * EMISSION_KG_PER_KM,
                         co2_net=safe_kg * CO2E_PER_KG_FOOD - km * EMISSION_KG_PER_KM)

    z = np.zeros(len(day), bool)
    tally("A", z, z, 0.0)
    sold = r2 & (u1 < u_sell); tally("B", sold, z, float((mrp[sold] * 0.6).sum()))                       # sale-only, fixed 40% off
    coll = r2 & (u2 < u_coll); o, n_, a_, t_ = routes_km(coll, idx, day, vend, vngo, vpos, False); tally("C", z, coll, 0.0, o, n_, a_, t_, km_used="nn")
    sold = (dec == "sell") & (u1 < u_sell); coll = (dec == "donate") & (u2 < u_coll)
    o, n_, a_, t_ = routes_km(coll, idx, day, vend, vngo, vpos, optimise)
    rev = float((mrp[sold] * (1 - disc[sold])).sum()); comp = float(kg[dec == "compost"].sum())
    tally("D_manualroute", sold, coll, rev, o, n_, a_, t_, comp, km_used="nn")
    tally("D", sold, coll, rev, o, n_, a_, t_, comp, km_used="opt" if optimise else "nn")
    return out


t0 = time.time(); runs = [run(1000 + i) for i in range(args.runs)]; print("sim seconds", round(time.time() - t0))
keys = list(runs[0]["D"].keys()); agg_sim = {}
for s in runs[0]:
    agg_sim[s] = {k: {"mean": float(np.mean([r[s][k] for r in runs])), "ci95": float(1.96 * np.std([r[s][k] for r in runs], ddof=1) / np.sqrt(len(runs)))} for k in keys}
R["simulation"] = {"runs": args.runs, "days": 30, "vendors": 40, "ngos": 3, "lots_per_vendor_day": 1.2, "u_sell": 0.6, "u_collect": 0.85,
                   "price_per_kg_inr": PPK, "fixed_discount_B": 0.4, "strategies": agg_sim}

# sensitivity (expected values; no routing needed)
kgp, safep = P["quantity_kg"], P["safe"]
def exp_div(strategy, us, uc):
    if strategy == "B": return (kgp * safep * P["r2"]).sum() * us / kgp.sum() * 100
    if strategy == "C": return (kgp * safep * P["r2"]).sum() * uc / kgp.sum() * 100
    return ((kgp * safep * (P["dec"] == "sell")).sum() * us + (kgp * safep * (P["dec"] == "donate")).sum() * uc) / kgp.sum() * 100
US, UC = [0.2, 0.4, 0.6, 0.8, 1.0], [0.4, 0.6, 0.85, 1.0]
grid = [[exp_div("D", us, uc) - max(exp_div("B", us, uc), exp_div("C", us, uc)) for uc in UC] for us in US]
R["sensitivity"] = {"u_sell": US, "u_collect": UC, "gain_pp_vs_best_baseline": grid,
                    "foodloop_pct": [[exp_div("D", us, uc) for uc in UC] for us in US]}
# sensitivity to CO2 factor and meal weight (net CO2 of D vs C)
sd = agg_sim
R["sensitivity_co2"] = {str(f): {"D": sd["D"]["safe_diverted_kg"]["mean"] * f - sd["D"]["co2_transport"]["mean"],
                                 "C": sd["C"]["safe_diverted_kg"]["mean"] * f - sd["C"]["co2_transport"]["mean"]} for f in [1.0, 2.0, 2.5, 3.0]}

# --- scenario figure: small multiples, one axis each
fig, axs = plt.subplots(1, 4, figsize=(6.5, 2.5))
order = ["A", "B", "C", "D"]; nm = ["Status\nquo", "Sale-only\napp", "Manual\ndonation", "FoodLoop\nAI"]
def bars(ax, key, title, scale=1.0, fmt="{:.1f}"):
    v = [agg_sim[s][key]["mean"] * scale for s in order]; e = [agg_sim[s][key]["ci95"] * scale for s in order]
    ax.bar(range(4), v, yerr=e, color=[STRAT_COL[s] for s in order], width=0.7, error_kw=dict(lw=0.9, capsize=2, ecolor=INK))
    ax.set_xticks(range(4)); ax.set_xticklabels(nm, fontsize=6.6); ax.set_title(title, fontsize=8.3, loc="left"); ax.grid(axis="x", visible=False)
    top = max(np.array(v) + np.array(e)); ax.set_ylim(min(0, min(v) * 1.2), top * 1.2)
    for i, x in enumerate(v): ax.text(i, x + (top * 0.03 if x >= 0 else -top * 0.03), fmt.format(x), ha="center", va="bottom" if x >= 0 else "top", fontsize=7.4)
bars(axs[0], "diversion_pct", "Safe food rescued\n(% of surplus kg)")
bars(axs[1], "unsafe_kg", "Unsafe food released\n(kg / 30 days)", fmt="{:.0f}")
bars(axs[2], "co2_net", "Net CO₂e avoided\n(kg / 30 days)", fmt="{:.0f}")
bars(axs[3], "ngo_km", "NGO pickup distance\n(km / 30 days)", fmt="{:.0f}")
fig.tight_layout(w_pad=0.8); save(fig, "benefit_scenarios")

# --- sensitivity heatmap
fig, ax = plt.subplots(figsize=(3.4, 2.5))
g = np.array(grid); vmax = max(abs(g).max(), 1)
ax.imshow(g, cmap=DIV, vmin=-vmax, vmax=vmax, aspect="auto"); ax.grid(False)
ax.set_xticks(range(len(UC))); ax.set_xticklabels([f"{int(u*100)}%" for u in UC]); ax.set_yticks(range(len(US))); ax.set_yticklabels([f"{int(u*100)}%" for u in US])
ax.set_xlabel("NGO collects a donated lot (probability)"); ax.set_ylabel("Citizen buys a listed lot (probability)")
for i in range(len(US)):
    for j in range(len(UC)): ax.text(j, i, f"{g[i, j]:+.1f}", ha="center", va="center", fontsize=8, color="white" if abs(g[i, j]) > vmax * 0.6 else INK)
for s in ax.spines.values(): s.set_visible(False)
fig.tight_layout(); save(fig, "sensitivity_heatmap")

# --- routing benchmark figure from the saved routing results
bj = ROOT / "docs" / "results.json"
if bj.exists():
    rt = json.loads(bj.read_text())["routing"]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    st_ = [r["stops"] for r in rt]
    for key, col, lab, mk in [("mean_baseline_km", C_GREY, "Acceptance order", "s"), ("mean_nearest_neighbour_km", C_ORANGE, "Nearest neighbour", "o"), ("mean_optimised_km", C_BLUE, "OR-Tools", "o")]:
        ax.plot(st_, [r[key] for r in rt], color=col, lw=2, marker=mk, ms=4.5)
        ax.text(st_[-1] + 0.3, rt[-1][key], lab, color=col, fontsize=8, va="center", fontweight="bold")
    ax.set_xlim(2.5, 17); ax.set_xticks(st_); ax.set_xlabel("Stops in the pickup batch"); ax.set_ylabel("Mean route length (km)")
    fig.tight_layout(); save(fig, "routing_benchmark")

(OUT / "results_paper.json").write_text(json.dumps(R, indent=2))
print(json.dumps({k: R[k] for k in ["deployed", "decision_quality", "robustness"]}, indent=1)[:3500])
print({s: {k: round(v["mean"], 1) for k, v in agg_sim[s].items() if k in ("diversion_pct", "unsafe_kg", "revenue_inr", "ngo_km", "co2_net", "wasted_kg")} for s in agg_sim})
