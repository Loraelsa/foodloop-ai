"""Experiment 4: API performance over real HTTP against a uvicorn process."""
import os, sys, time, json, subprocess, statistics as st, tempfile, threading
import httpx, psutil
ROOT = os.path.join(os.path.dirname(__file__), "..")
PORT = 8765; BASE = f"http://127.0.0.1:{PORT}"
dbfile = os.path.join(tempfile.mkdtemp(), "bench.db")
env = dict(os.environ, FOODLOOP_DB="sqlite:///" + dbfile)
t_start = time.perf_counter()
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "error"], cwd=ROOT, env=env)
cold = None
for _ in range(200):
    try:
        if httpx.get(BASE + "/health", timeout=0.5).status_code == 200: cold = time.perf_counter() - t_start; break
    except Exception: time.sleep(0.05)
ps = psutil.Process(proc.pid)
def cpu(): t = ps.cpu_times(); return t.user + t.system
c = httpx.Client(base_url=BASE, timeout=30)
tok = lambda e: {"Authorization": "Bearer " + c.post("/auth/login", json={"email": e, "password": "demo-password"}).json()["token"]}
V, CU = tok("vendor@demo"), tok("customer@demo")
BODY = dict(vendor_id=1, item="Veg Biryani", category="cooked", storage="hot", temp=30, hours=2, qty=10, unit="portions", kg_per_unit=0.4, mrp=200)
def pct(a, p): a = sorted(a); return a[min(len(a) - 1, int(len(a) * p))]
res = dict(cold_start_s=cold, rss_mb_idle=ps.memory_info().rss / 1e6)

# 1. create listing (ML inference + DB write)
lat = []; c0 = cpu()
for i in range(400):
    b = {**BODY, "item": f"Item {i}", "hours": (i % 6) + 0.5, "category": ["cooked", "bakery", "dairy", "produce", "sweets", "packaged"][i % 6]}
    s = time.perf_counter(); r = c.post("/listings", json=b, headers=V); lat.append((time.perf_counter() - s) * 1000); assert r.status_code == 200
res["create"] = dict(n=len(lat), median=st.median(lat), p95=pct(lat, .95), p99=pct(lat, .99), cpu_ms_per_req=(cpu() - c0) / len(lat) * 1000)

# 2. load orders so the impact query has work to do
sells = c.get("/listings?decision=sell&limit=200").json()
for i in range(1500):
    l = sells[i % len(sells)]
    c.post("/orders", json={"listing_id": l["id"], "qty": 0.01}, headers=CU)
# 3. impact: no cache vs cache
def timeit(path, n):
    L = []; c0 = cpu()
    for _ in range(n):
        s = time.perf_counter(); r = c.get(path); L.append((time.perf_counter() - s) * 1000); assert r.status_code == 200
    return dict(median=st.median(L), p95=pct(L, .95), cpu_ms_per_req=(cpu() - c0) / n * 1000)
res["impact_nocache"] = timeit("/impact?use_cache=false", 300)
c.get("/impact"); res["impact_cache"] = timeit("/impact", 300)
res["health"] = c.get("/health").json()

# 4. payload size with / without gzip
a = c.get("/listings?decision=sell&limit=200", headers={"Accept-Encoding": "identity"})
b = c.get("/listings?decision=sell&limit=200", headers={"Accept-Encoding": "gzip"})
res["payload"] = dict(raw=len(a.content), gzip=int(b.headers.get("content-length", len(b.content))), encoding=b.headers.get("content-encoding"))
res["list_latency_gzip_off"] = None

# 5. throughput with 8 client threads
def worker(out):
    cl = httpx.Client(base_url=BASE, timeout=30)
    for _ in range(60): cl.get("/listings?decision=sell&limit=50")
    out.append(1)
c0 = cpu(); t0 = time.perf_counter(); done = []; th = [threading.Thread(target=worker, args=(done,)) for _ in range(8)]
[t.start() for t in th]; [t.join() for t in th]; dt = time.perf_counter() - t0
res["throughput"] = dict(requests=8 * 60, seconds=dt, rps=8 * 60 / dt, cpu_ms_per_req=(cpu() - c0) / (8 * 60) * 1000)
res["rss_mb_end"] = ps.memory_info().rss / 1e6
proc.terminate(); proc.wait()

# 6. index effect (in-process, 20k rows)
sys.path.insert(0, ROOT)
os.environ["FOODLOOP_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "idx.db")
from app import db
db.Base.metadata.create_all(db.engine)
import random, datetime as dt_
from sqlalchemy import text
with db.SessionLocal() as s:
    s.add(db.Vendor(name="v", locality="x", lat=0, lng=0)); s.commit()
    rows = [db.Listing(vendor_id=1, item="i", category="cooked", storage="hot", temp=30, hours=1, qty=1, unit="u", kg_per_unit=.4, mrp=100, remaining=5,
                       decision=random.choice(["sell", "donate", "compost"]), discount=20, price=80, status=random.choice(["live", "sold", "claimed", "composted"]) if random.random() < .9 else "live",
                       expires=dt_.datetime.utcnow() + dt_.timedelta(hours=random.random() * 30)) for _ in range(50000)]
    s.bulk_save_objects(rows); s.commit()
    def q():
        return s.query(db.Listing).filter(db.Listing.status == "live", db.Listing.decision == "donate").order_by(db.Listing.expires).limit(200).all()
    def bench(n=60):
        L = []
        for _ in range(n):
            t = time.perf_counter(); q(); L.append((time.perf_counter() - t) * 1000); s.expire_all()
        return st.median(L)
    with_idx = bench()
    s.execute(text("DROP INDEX ix_listing_live_decision")); s.execute(text("DROP INDEX IF EXISTS ix_listings_status")); s.execute(text("DROP INDEX IF EXISTS ix_listings_decision")); s.commit()
    without = bench()
res["index"] = dict(rows=50000, with_index_ms=with_idx, without_index_ms=without)
json.dump(res, open(os.path.join(ROOT, "bench", "out", "api.json"), "w"), indent=1)
print(json.dumps({k: (v if not isinstance(v, float) else round(v, 3)) for k, v in res.items()}, indent=1, default=lambda x: round(x, 3)))
