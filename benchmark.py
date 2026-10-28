"""Generates the measured results used in the report.  Run from backend/:  python ../scripts/benchmark.py
Outputs docs/results.json and docs/results.md.  Every number in the paper's Results section should come from here."""
import json
import os
import statistics as st
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(suffix='.db', delete=False).name}"

from fastapi.testclient import TestClient  # noqa: E402

from app import metrics  # noqa: E402
from app.config import EMISSION_KG_PER_KM  # noqa: E402
from app.main import app  # noqa: E402
from app.ml import train  # noqa: E402
from app.routing import _matrix, plan_route, route_length_m  # noqa: E402

rng = np.random.default_rng(2026)
out = {}

# 1) ML model comparison ------------------------------------------------------------------------------
out["model_comparison"] = train.main()

# 2) Routing: OR-Tools vs manual (acceptance-order) dispatch, random Delhi-NCR instances ---------------
BBOX = (28.40, 28.80, 76.95, 77.45)  # lat_min, lat_max, lon_min, lon_max
rows = []
for n_stops in (3, 5, 8, 12):
    saved_pct, opt_km, base_km, solve_ms, nn_km = [], [], [], [], []
    for _ in range(40):
        pts = [(rng.uniform(BBOX[0], BBOX[1]), rng.uniform(BBOX[2], BBOX[3])) for _ in range(n_stops + 1)]
        stops = [{"id": i, "lat": p[0], "lon": p[1], "kg": 5, "name": f"s{i}"} for i, p in enumerate(pts[1:])]
        t0 = time.perf_counter()
        r = plan_route(pts[0], stops, time_limit_ms=200)
        solve_ms.append((time.perf_counter() - t0) * 1000)
        opt_km.append(r["distance_km"]); base_km.append(r["baseline_km"])
        m = _matrix(pts); cur, seen, order = 0, {0}, [0]      # nearest-neighbour: a sensible human dispatcher
        while len(seen) < len(pts):
            nxt = min((j for j in range(len(pts)) if j not in seen), key=lambda j: m[cur][j])
            order.append(nxt); seen.add(nxt); cur = nxt
        nn_km.append(route_length_m(order + [0], m) / 1000)
        saved_pct.append(100 * r["saved_km"] / r["baseline_km"] if r["baseline_km"] else 0)
    rows.append({"stops": n_stops, "instances": 40, "mean_baseline_km": round(st.mean(base_km), 1), "mean_nearest_neighbour_km": round(st.mean(nn_km), 1),
                 "mean_saved_vs_nearest_neighbour_pct": round(100 * (st.mean(nn_km) - st.mean(opt_km)) / st.mean(nn_km), 1),
                 "mean_optimised_km": round(st.mean(opt_km), 1), "mean_distance_saved_pct": round(st.mean(saved_pct), 1),
                 "mean_co2_saved_kg_per_route": round((st.mean(base_km) - st.mean(opt_km)) * EMISSION_KG_PER_KM, 2),
                 "mean_solve_ms": round(st.mean(solve_ms), 0)})
out["routing"] = rows

# 3) API latency + caching ------------------------------------------------------------------------------
with TestClient(app) as c:
    def reg(role, i, lat=28.6, lon=77.2):
        r = c.post("/api/auth/register", json={"name": f"{role}{i}", "email": f"{role}{i}@b.com", "password": "bench-" + __import__("os").urandom(4).hex(),
                                              "role": role, "lat": lat, "lon": lon})
        return {"Authorization": "Bearer " + r.json()["token"]}
    vh = reg("vendor", 0)
    cats = ["cooked_meal", "bakery", "dairy", "produce", "packaged", "dessert"]
    lat_pred = []
    for i in range(300):  # seed data + measure the ML endpoint under a realistic call
        body = dict(item_name=f"item{i}", category=cats[i % 6], quantity_kg=float(1 + i % 9), mrp=100.0,
                    hours_since_prepared=float(rng.uniform(0, 12)), storage="ambient", ambient_temp_c=30.0)
        t0 = time.perf_counter(); c.post("/api/listings", json=body, headers=vh)
        lat_pred.append((time.perf_counter() - t0) * 1000)

    def timeit(fn, n=300):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter(); fn(); ts.append((time.perf_counter() - t0) * 1000)
        ts.sort(); return {"p50_ms": round(ts[n // 2], 2), "p95_ms": round(ts[int(n * .95)], 2), "mean_ms": round(st.mean(ts), 2)}

    uncached = timeit(lambda: (metrics.invalidate(), c.get("/api/impact")))
    metrics.invalidate(); c.get("/api/impact")
    cached = timeit(lambda: c.get("/api/impact"))
    out["api_latency"] = {
        "create_listing_incl_ml_and_db_write": {"p50_ms": round(sorted(lat_pred)[150], 2), "p95_ms": round(sorted(lat_pred)[285], 2)},
        "impact_no_cache": uncached, "impact_with_cache": cached,
        "cache_speedup_x": round(uncached["mean_ms"] / cached["mean_ms"], 1),
    }
    # payload size with/without gzip
    raw = c.get("/api/impact", headers={"Accept-Encoding": "identity"})
    out["payload_bytes_impact"] = len(raw.content)
    lst = c.get("/api/listings/mine", headers={**vh, "Accept-Encoding": "identity"})
    gz = c.get("/api/listings/mine", headers={**vh, "Accept-Encoding": "gzip"})
    out["gzip_listings_payload"] = {"uncompressed_bytes": len(lst.content),
                                    "transfer_bytes_gzip": int(gz.headers.get("content-length", 0)) or len(gz.content)}
    out["system_metrics"] = c.get("/api/system/metrics").json()

(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "results.json").write_text(json.dumps(out, indent=2))
print(json.dumps({k: v for k, v in out.items() if k != "model_comparison"}, indent=2))
