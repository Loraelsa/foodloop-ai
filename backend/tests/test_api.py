from .conftest import TEST_PW, make_user

FRESH = dict(item_name="Paneer wrap", category="cooked_meal", quantity_kg=5, mrp=400,
             hours_since_prepared=1, storage="ambient", ambient_temp_c=28)
MID = dict(item_name="Veg biryani", category="cooked_meal", quantity_kg=8, mrp=600,
           hours_since_prepared=4.0, storage="ambient", ambient_temp_c=28)
OLD = dict(item_name="Old curd", category="dairy", quantity_kg=2, mrp=100,
           hours_since_prepared=30, storage="ambient", ambient_temp_c=32)


def test_TC01_register_login_and_duplicate_email(client):
    h, u = make_user(client, "vendor")
    r = client.post("/api/auth/login", json={"email": u["email"], "password": TEST_PW})
    assert r.status_code == 200 and r.json()["user"]["role"] == "vendor"
    dup = client.post("/api/auth/register", json={"name": "x y", "email": u["email"], "password": TEST_PW, "role": "ngo"})
    assert dup.status_code == 409


def test_TC02_wrong_password_rejected(client):
    _, u = make_user(client, "citizen")
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "nope-nope"}).status_code == 401


def test_TC03_protected_route_needs_token(client):
    assert client.get("/api/me").status_code == 401


def test_TC04_role_enforcement(client):
    h, _ = make_user(client, "citizen")
    assert client.post("/api/listings", json=FRESH, headers=h).status_code == 403


def test_TC05_fresh_item_is_sell_with_discounted_price(client):
    h, _ = make_user(client, "vendor")
    r = client.post("/api/listings", json=FRESH, headers=h)
    assert r.status_code == 201
    d = r.json()
    assert d["decision"] == "sell" and 0 < d["price"] < FRESH["mrp"] and d["discount_pct"] >= 20


def test_TC06_nearly_expired_item_is_compost(client):
    h, _ = make_user(client, "vendor")
    assert client.post("/api/listings", json=OLD, headers=h).json()["decision"] == "compost"


def test_TC07_mid_life_item_is_donate_and_free(client):
    h, _ = make_user(client, "vendor")
    d = client.post("/api/listings", json=MID, headers=h).json()
    assert d["decision"] == "donate" and d["price"] == 0


def test_TC08_invalid_input_rejected(client):
    h, _ = make_user(client, "vendor")
    bad = {**FRESH, "quantity_kg": -3}
    assert client.post("/api/listings", json=bad, headers=h).status_code == 422
    assert client.post("/api/listings", json={**FRESH, "category": "pizza"}, headers=h).status_code == 422


def test_TC09_citizen_sees_and_reserves_sell_items(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    ch, _ = make_user(client, "citizen")
    assert any(x["id"] == lid for x in client.get("/api/market", headers=ch).json())
    assert client.post(f"/api/listings/{lid}/reserve", headers=ch).status_code == 200
    ch2, _ = make_user(client, "citizen")
    assert client.post(f"/api/listings/{lid}/reserve", headers=ch2).status_code == 409  # already taken


def test_TC10_ngo_accept_builds_optimised_route_and_completes(client):
    vendors = [make_user(client, "vendor", f"V{i}", lat=28.55 + i * 0.03, lon=77.15 + ((-1) ** i) * 0.05 * i)
               for i in range(5)]
    ids = [client.post("/api/listings", json=MID, headers=h).json()["id"] for h, _ in vendors]
    nh, _ = make_user(client, "ngo", lat=28.61, lon=77.20)
    assert set(ids) <= {d["id"] for d in client.get("/api/donations", headers=nh).json()}
    r = client.post("/api/ngo/accept", json={"listing_ids": ids}, headers=nh)
    assert r.status_code == 201
    p = r.json()
    assert p["distance_km"] <= p["baseline_km"] + 1e-6           # optimiser never worse than manual order
    stops = [s["listing_id"] for s in p["route"]["routes"][0] if s["listing_id"]]
    assert sorted(stops) == sorted(ids)                          # every stop visited exactly once
    # can't accept twice
    assert client.post("/api/ngo/accept", json={"listing_ids": ids[:1]}, headers=nh).status_code == 409
    assert client.post(f"/api/ngo/pickups/{p['id']}/complete", headers=nh).status_code == 200


def test_TC11_capacity_infeasible_returns_422(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json={**MID, "quantity_kg": 50}, headers=vh).json()["id"]
    nh, _ = make_user(client, "ngo")
    r = client.post("/api/ngo/accept", json={"listing_ids": [lid], "capacity_kg": 10}, headers=nh)
    assert r.status_code == 422


def test_TC12_impact_counts_completed_only_and_is_cached(client):
    before = client.get("/api/impact").json()
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=MID, headers=vh).json()["id"]
    nh, _ = make_user(client, "ngo")
    pid = client.post("/api/ngo/accept", json={"listing_ids": [lid]}, headers=nh).json()["id"]
    mid = client.get("/api/impact").json()
    assert mid["kg_donated"] == before["kg_donated"]              # accepted but not yet collected
    client.post(f"/api/ngo/pickups/{pid}/complete", headers=nh)
    after = client.get("/api/impact").json()
    assert round(after["kg_donated"] - before["kg_donated"], 2) == MID["quantity_kg"]
    assert after["meals_redistributed"] > before["meals_redistributed"]
    client.get("/api/impact"); client.get("/api/impact")
    assert client.get("/api/system/metrics").json()["cache_hits"] >= 2
