"""Experiment 1: shelf-life model comparison (synthetic labels) + ablation + decision-policy comparison."""
import sys, time, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np, xgboost as xgb
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score, f1_score, confusion_matrix, precision_recall_fscore_support
from app import shelf

OUT = os.path.join(os.path.dirname(__file__), "out"); os.makedirs(OUT, exist_ok=True)
P_CORE_W = 15.0   # assumed active power per CPU core (W): ESTIMATE used for energy figures

d = shelf.synth(20000, 42)
X = shelf.encode(d["category"], d["storage"], d["temp"], d["hours"], d["qty"])
y = d["remaining"]
rng = np.random.default_rng(7); idx = rng.permutation(len(y)); cut = int(0.8 * len(y))
tr, te = idx[:cut], idx[cut:]
Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
kg_te = (d["qty"])[te]
cls = lambda a: np.array([shelf.CLASSES.index(shelf.decide_from_hours(v)) for v in a])
ctrue = cls(yte)


def policy_metrics(pred_cls, true_rem, kg):
    """pred_cls: 0 compost,1 donate,2 sell. Edible = true remaining >= 1 h. Sell requires >= 4 h, donate >= 1 h."""
    dist = pred_cls > 0
    fit = ((pred_cls == 2) & (true_rem >= shelf.SELL_H)) | ((pred_cls == 1) & (true_rem >= shelf.DONATE_H))
    edible = true_rem >= shelf.DONATE_H
    rec = kg[fit].sum() / kg[edible].sum() * 100
    unsafe = kg[dist & ~fit].sum() / max(kg[dist].sum(), 1e-9) * 100
    return rec, unsafe


def run(name, mk, Xa=Xtr, Xb=Xte):
    m = mk()
    t0 = time.process_time(); w0 = time.perf_counter(); m.fit(Xa, ytr); cpu = time.process_time() - t0; wall = time.perf_counter() - w0
    p = m.predict(Xb)
    one = Xb[:1]; lat = []
    for _ in range(300):
        s = time.perf_counter(); m.predict(one); lat.append((time.perf_counter() - s) * 1000)
    pc = cls(p)
    rec, uns = policy_metrics(pc, yte, kg_te)
    return dict(model=name, rmse=float(np.sqrt(mean_squared_error(yte, p))), r2=float(r2_score(yte, p)),
                acc=float((pc == ctrue).mean() * 100), f1=float(f1_score(ctrue, pc, average="macro")),
                recovered=float(rec), unsafe=float(uns), train_cpu_s=cpu, train_wall_s=wall,
                infer_ms=float(np.median(lat)), kwh=cpu * P_CORE_W / 3.6e6, _m=m, _pc=pc)

mk_xgb = lambda: xgb.XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.08, subsample=0.9, colsample_bytree=0.9, n_jobs=1, random_state=42)
res = [run("Linear regression", lambda: LinearRegression()),
       run("Random forest", lambda: RandomForestRegressor(n_estimators=200, max_depth=14, n_jobs=1, random_state=42)),
       run("XGBoost (deployed)", mk_xgb)]
for r in res:
    import tempfile, pickle
    r["size_kb"] = (len(pickle.dumps(r["_m"])) / 1024)

# baselines: age-cut-off rules tuned on the training split subject to <=10 % unsafe
hrs_tr, hrs_te = d["hours"][tr], d["hours"][te]
kg_tr = d["qty"][tr]
def tune_global():
    best = None
    grid = np.unique(np.round(np.quantile(hrs_tr, np.linspace(0.02, 0.98, 40)), 2))
    for t1 in grid:
        for t2 in grid:
            if t2 < t1: continue
            pc = np.where(hrs_tr < t1, 2, np.where(hrs_tr < t2, 1, 0))
            rec, uns = policy_metrics(pc, y[tr], kg_tr)
            if uns <= 10 and (best is None or rec > best[0]): best = (rec, t1, t2)
    return best
bg = tune_global()
pc_g = np.where(hrs_te < bg[1], 2, np.where(hrs_te < bg[2], 1, 0))
cat_te = d["category"][te]; cat_tr = d["category"][tr]
pc_c = np.zeros(len(yte), int); cuts = {}
for c in shelf.CATEGORIES:
    mtr = cat_tr == c; h = hrs_tr[mtr]; best = None
    grid = np.unique(np.round(np.quantile(h, np.linspace(0.02, 0.98, 30)), 2))
    for t1 in grid:
        for t2 in grid:
            if t2 < t1: continue
            pc = np.where(h < t1, 2, np.where(h < t2, 1, 0))
            rec, uns = policy_metrics(pc, y[tr][mtr], kg_tr[mtr])
            if uns <= 10 and (best is None or rec > best[0]): best = (rec, t1, t2)
    if best is None: best = (0, 0, 0)
    cuts[c] = best; mte = cat_te == c
    pc_c[mte] = np.where(hrs_te[mte] < best[1], 2, np.where(hrs_te[mte] < best[2], 1, 0))
base = []
for nm, pc in (("Manual rule, global age cut-offs", pc_g), ("Manual rule, per-category cut-offs", pc_c)):
    rec, uns = policy_metrics(pc, yte, kg_te)
    base.append(dict(model=nm, acc=float((pc == ctrue).mean() * 100), f1=float(f1_score(ctrue, pc, average="macro")), recovered=float(rec), unsafe=float(uns)))

# ablation with XGBoost
abl = []
names = shelf.FEATURE_NAMES
groups = {"All inputs (deployed)": [], "Without food category": [i for i, n in enumerate(names) if n.startswith("cat_")],
          "Without storage type": [i for i, n in enumerate(names) if n.startswith("sto_")], "Without room temperature": [names.index("temp_c")],
          "Without quantity": [names.index("qty_kg")], "Hours since prepared only": [i for i, n in enumerate(names) if n != "hours_since_prep"]}
for g, drop in groups.items():
    keep = [i for i in range(len(names)) if i not in drop]
    r = run(g, mk_xgb, Xtr[:, keep], Xte[:, keep])
    abl.append({k: v for k, v in r.items() if not k.startswith("_")})

# margin trade-off, per-class metrics, importance, confusion
xg = res[2]["_m"]; p = xg.predict(Xte)
margins = []
for mg in (0, 0.5, 1, 1.5, 2, 3):
    pc = cls(p - mg); rec, uns = policy_metrics(pc, yte, kg_te); margins.append(dict(margin=mg, recovered=float(rec), unsafe=float(uns), acc=float((pc == ctrue).mean() * 100)))
cm = confusion_matrix(ctrue, res[2]["_pc"], labels=[0, 1, 2]).tolist()
prec, rec_, f1c, sup = precision_recall_fscore_support(ctrue, res[2]["_pc"], labels=[0, 1, 2])
imp = dict(zip(names, map(float, xg.feature_importances_)))
cat_imp = {"Food category": sum(v for k, v in imp.items() if k.startswith("cat_")), "Storage": sum(v for k, v in imp.items() if k.startswith("sto_")),
           "Room temperature": imp["temp_c"], "Hours since prepared": imp["hours_since_prep"], "Quantity": imp["qty_kg"]}
mix = {c: float((ctrue == i).mean() * 100) for i, c in enumerate(shelf.CLASSES)}
from scipy.stats import spearmanr
rho_age = float(spearmanr(d["hours"], cls(y))[0]); rho_rem = float(spearmanr(y, cls(y))[0])
out = dict(models=[{k: v for k, v in r.items() if not k.startswith("_")} for r in res], baselines=base, global_cuts=bg, ablation=abl, margins=margins,
           confusion=cm, per_class=dict(precision=list(map(float, prec)), recall=list(map(float, rec_)), f1=list(map(float, f1c)), support=list(map(int, sup))),
           importance=cat_imp, mix=mix, n_train=int(cut), n_test=int(len(y) - cut), rho_age=rho_age, rho_rem=rho_rem, P_CORE_W=P_CORE_W)
out["cat_cuts"] = {k: [float(x) for x in v] for k, v in cuts.items()}
json.dump(out, open(os.path.join(OUT, "models.json"), "w"), indent=1)
for r in out["models"]: print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
print("baselines", base); print("margins", margins); print("per-class", out["per_class"]); print("mix", mix, "rho", rho_age, rho_rem)
