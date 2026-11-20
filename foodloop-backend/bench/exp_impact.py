"""Experiment 6: simulated impact (ESTIMATE). 100 vendors x 30 days x 2 items/day, hidden true shelf life; policies scored on identical food."""
import sys, os, json, time, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app import shelf, ml, routing, seed, impact as imp
M = json.load(open(os.path.join(os.path.dirname(__file__), "out", "models.json")))
cuts = M["cat_cuts"]
model = ml.load_shelf()
PRICE = {"cooked": 350, "bakery": 300, "dairy": 150, "produce": 80, "sweets": 600, "packaged": 250}   # INR/kg, ASSUMED
locs = list(seed.LOCALITY_XY.values()); depots = [(n["lat"], n["lng"]) for n in seed.NGOS] + [(12.9560, 77.5990)]
NV, DAYS, PER = 100, 30, 2
UPTAKE = float(os.environ.get("UPTAKE", 1.0))

def one_rep(rep, route_time_ms=100):
    rng = np.random.default_rng(1000 + rep); random.seed(1000 + rep)
    d = shelf.synth(NV * DAYS * PER, 9000 + rep)               # unseen seeds, not the training seed
    n = len(d["qty"]); vend = rng.integers(0, NV, n)
    vloc = [random.choice(locs) for _ in range(NV)]; vpos = [(a + random.uniform(-.008, .008), b + random.uniform(-.008, .008)) for a, b in vloc]
    day = np.repeat(np.arange(DAYS), NV * PER)
    X = shelf.encode(d["category"], d["storage"], d["temp"], d["hours"], d["qty"]); pred = model.predict(X)
    true = d["remaining"]; kg = d["qty"]; cat = d["category"]; hours = d["hours"]
    edible = true >= shelf.DONATE_H
    out = {}
    def score(name, pc, pred_rem=None, accept_route=False):
        fit = ((pc == 2) & (true >= shelf.SELL_H)) | ((pc == 1) & (true >= shelf.DONATE_H))
        dist = pc > 0
        rec_kg = (kg * fit).sum() * UPTAKE
        unsafe = kg[dist & ~fit].sum() / max(kg[dist].sum(), 1e-9) * 100
        # revenue: sold, fit items at the dynamic discount (FoodLoop) or 50 % (rule baselines have no sale channel)
        rev = 0.0
        if pred_rem is not None:
            disc = np.array([shelf.discount_pct(r) for r in pred_rem]) / 100
            m = fit & (pc == 2); rev = float((kg[m] * np.array([PRICE[c] for c in cat[m]]) * (1 - disc[m])).sum()) * UPTAKE
        # donation routes: one route per NGO per day over the vendors that donated
        km = 0.0
        don = np.where(dist & (pc == 1) & fit)[0]
        for dd in range(DAYS):
            ids = [i for i in don if day[i] == dd]
            if not ids: continue
            groups = {}
            for i in ids:
                p = vpos[vend[i]]; g = min(range(3), key=lambda k: routing.road(depots[k], p)); groups.setdefault(g, set()).add(vend[i])
            for g, vs in groups.items():
                pts = [vpos[v] for v in sorted(vs)]
                if accept_route: km += routing.accept_order(depots[g], pts)[1]
                else: km += routing.ortools_route(depots[g], pts, route_time_ms)[0] and routing.ortools_route(depots[g], pts, route_time_ms)[1] if False else routing.ortools_route(depots[g], pts, route_time_ms)[1]
        im = imp.impact(rec_kg, km)
        out[name] = dict(edible_kg=float(kg[edible].sum()) / DAYS, rec_kg=rec_kg / DAYS, rec_pct=rec_kg / UPTAKE / kg[edible].sum() * 100 if UPTAKE else 0, unsafe=unsafe, meals=im["meals"] / DAYS,
                         co2_net=im["co2_net"] / DAYS, km=km / DAYS, rev=rev / DAYS, binned=(kg.sum() - rec_kg) / DAYS)
    score("No system (all binned)", np.zeros(n, int))
    pcm = np.zeros(n, int)
    for c, (rr, t1, t2) in cuts.items():
        mm = cat == c; pcm[mm] = np.where(hours[mm] < t1, 2, np.where(hours[mm] < t2, 1, 0))
    score("Manual rule, per-category cut-offs", pcm, None, accept_route=True)
    pcf = np.array([shelf.CLASSES.index(shelf.decide_from_hours(v)) for v in pred])
    score("FoodLoop AI", pcf, pred)
    pcs = np.array([shelf.CLASSES.index(shelf.decide_from_hours(v - 1.0)) for v in pred])
    score("FoodLoop AI, 1 h safety margin", pcs, pred - 1.0)
    return out

R = int(os.environ.get("REPS", 8))
reps = [one_rep(r) for r in range(R)]
names = list(reps[0].keys()); keys = list(reps[0][names[0]].keys())
summ = {nm: {k: (float(np.mean([r[nm][k] for r in reps])), float(1.96 * np.std([r[nm][k] for r in reps], ddof=1) / np.sqrt(R))) for k in keys} for nm in names}
res = dict(reps=R, uptake=UPTAKE, vendors=NV, days=DAYS, items_per_vendor_day=PER, summary=summ, price_per_kg=PRICE)
fn = "impact.json" if UPTAKE == 1.0 else f"impact_u{int(UPTAKE*100)}.json"
json.dump(res, open(os.path.join(os.path.dirname(__file__), "out", fn), "w"), indent=1)
for nm in names:
    s = summ[nm]; print(f"{nm:38s} edible {s['edible_kg'][0]:.0f} rec {s['rec_kg'][0]:.0f} kg ({s['rec_pct'][0]:.1f}%) unsafe {s['unsafe'][0]:.1f}% meals {s['meals'][0]:.0f} CO2 {s['co2_net'][0]:.0f} km {s['km'][0]:.0f} rev {s['rev'][0]:.0f}")
