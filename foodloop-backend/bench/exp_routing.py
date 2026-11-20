"""Experiment 3: pickup routing. Acceptance order vs nearest neighbour vs OR-Tools (200 ms), plus exact optimum for small routes."""
import sys, os, json, time, itertools, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app import routing, seed

random.seed(2026); np.random.seed(2026)
locs = list(seed.LOCALITY_XY.values())
depots = [(n["lat"], n["lng"]) for n in seed.NGOS] + [(12.9560, 77.5990)]
def stops(n):
    return [(random.choice(locs)[0] + random.uniform(-0.008, 0.008), random.choice(locs)[1] + random.uniform(-0.008, 0.008)) for _ in range(n)]
# NOTE: lat/lng chosen independently per axis would mix localities; use a single choice per stop instead
def stops(n):
    out = []
    for _ in range(n):
        la, ln = random.choice(locs); out.append((la + random.uniform(-0.008, 0.008), ln + random.uniform(-0.008, 0.008)))
    return out

rows = []
for n in range(2, 15):
    for rep in range(26):
        dp = random.choice(depots); pts = stops(n)
        _, a = routing.accept_order(dp, pts); _, nn = routing.nearest_neighbour(dp, pts)
        t = time.perf_counter(); _, o = routing.ortools_route(dp, pts, 200); ms = (time.perf_counter() - t) * 1000
        rows.append(dict(n=n, accept=a, nn=nn, ort=o, ms=ms))
print("routes", len(rows))
import pandas as pd
df = pd.DataFrame(rows)
def bucket(n): return "2-4" if n <= 4 else "5-7" if n <= 7 else "8-10" if n <= 10 else "11-14"
df["bucket"] = df.n.map(bucket)
g = df.groupby("bucket", sort=False).agg(routes=("n", "size"), accept=("accept", "mean"), nn=("nn", "mean"), ort=("ort", "mean"), ms=("ms", "mean"), ms_max=("ms", "max"))
g.loc["All"] = [len(df), df.accept.mean(), df.nn.mean(), df.ort.mean(), df.ms.mean(), df.ms.max()]
g["save_vs_accept"] = (1 - g.ort / g.accept) * 100; g["save_vs_nn"] = (1 - g.ort / g.nn) * 100
print(g.round(2).to_string())
worse = float((df.ort > df.nn + 1e-9).mean() * 100); print("ort worse than nn %", worse)

# exact optimum for n <= 8 (brute force over permutations)
ex = []
for _ in range(60):
    n = random.randint(4, 8); dp = random.choice(depots); pts = stops(n)
    best = min(routing.length(dp, pts, p) for p in itertools.permutations(range(n)))
    _, nn = routing.nearest_neighbour(dp, pts); _, o = routing.ortools_route(dp, pts, 200); _, a = routing.accept_order(dp, pts)
    ex.append(dict(n=n, best=best, nn=nn, ort=o, accept=a))
e = pd.DataFrame(ex)
gap = dict(ort_mean=float(((e.ort / e.best - 1) * 100).mean()), nn_mean=float(((e.nn / e.best - 1) * 100).mean()), accept_mean=float(((e.accept / e.best - 1) * 100).mean()),
           ort_optimal=float(((e.ort / e.best - 1) < 1e-6).mean() * 100), nn_optimal=float(((e.nn / e.best - 1) < 1e-6).mean() * 100), n_routes=len(e))
print("gap", gap)
out = dict(table=g.reset_index().rename(columns={"index": "bucket"}).to_dict("records"), worse_than_nn_pct=worse, gap=gap, raw=rows)
json.dump(out, open(os.path.join(os.path.dirname(__file__), "out", "routing.json"), "w"))
