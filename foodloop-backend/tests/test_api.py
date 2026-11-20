import os, tempfile, pytest
os.environ["FOODLOOP_DB"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app.main import app

BODY = dict(vendor_id=1, item="Veg Biryani", category="cooked", storage="hot", temp=30, hours=2, qty=10, unit="portions", kg_per_unit=0.4, mrp=200)


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as cl:
        yield cl


def H(c, email):
    t = c.post("/auth/login", json={"email": email, "password": "demo-password"}).json()["token"]
    return {"Authorization": "Bearer " + t}


def test_TC01_login_rejects_bad_password(c):
    assert c.post("/auth/login", json={"email": "vendor@demo", "password": "x"}).status_code == 401


def test_TC02_listing_requires_token(c):
    assert c.post("/listings", json=BODY).status_code == 401


def test_TC03_customer_cannot_create_listing(c):
    assert c.post("/listings", json=BODY, headers=H(c, "customer@demo")).status_code == 403


def test_TC04_fresh_item_is_sell_with_discount(c):
    r = c.post("/listings", json=BODY, headers=H(c, "vendor@demo")).json()
    assert r["decision"] == "sell" and 20 <= r["discount"] <= 70 and r["price"] < 200


def test_TC05_old_item_is_compost_without_discount(c):
    r = c.post("/listings", json={**BODY, "hours": 40}, headers=H(c, "vendor@demo")).json()
    assert r["decision"] == "compost" and r["discount"] == 0


def test_TC06_borderline_item_is_donate(c):
    # cooked, hot, 30C: safe life is about 6.8 h (6 h base x 1.6 hot-held x 0.5^0.5), so 4.5 h of age leaves about 2.3 h -> donate window
    r = c.post("/listings", json={**BODY, "hours": 4.5, "item": "Borderline"}, headers=H(c, "vendor@demo")).json()
    assert r["decision"] == "donate"


def test_TC07_invalid_category_rejected(c):
    assert c.post("/listings", json={**BODY, "category": "pizza"}, headers=H(c, "vendor@demo")).status_code == 422


def test_TC08_negative_quantity_rejected(c):
    assert c.post("/listings", json={**BODY, "qty": -1}, headers=H(c, "vendor@demo")).status_code == 422


def test_TC09_order_reduces_stock_and_returns_code(c):
    sl = c.get("/listings?decision=sell").json()
    before = sl[0]["qty"]
    o = c.post("/orders", json={"listing_id": sl[0]["id"], "qty": 2}, headers=H(c, "customer@demo")).json()
    assert len(o["code"]) == 4
    after = [x for x in c.get("/listings?decision=sell").json() if x["id"] == sl[0]["id"]][0]["qty"]
    assert after == before - 2


def test_TC10_overorder_rejected(c):
    sl = c.get("/listings?decision=sell").json()
    assert c.post("/orders", json={"listing_id": sl[0]["id"], "qty": 9999}, headers=H(c, "customer@demo")).status_code == 409


def _donations(c, n=3):
    ids = []
    for v in (2, 3, 6, 8)[:n]:
        r = c.post("/listings", json={**BODY, "vendor_id": v, "hours": 4.5, "item": f"Don{v}", "qty": 8}, headers=H(c, "vendor@demo")).json()
        assert r["decision"] == "donate"
        ids.append(r["id"])
    return ids


def test_TC11_route_visits_all_stops_and_is_no_longer_than_acceptance_order(c):
    ids = _donations(c)
    p = c.post("/pickups/plan", json={"ngo_id": 1, "listing_ids": ids}, headers=H(c, "ngo@demo")).json()
    assert set(p["order"]) == set(ids) and p["km"] <= p["naive_km"] + 1e-6


def test_TC12_capacity_limit_enforced(c):
    ids = _donations(c, 4)
    big = c.post("/listings", json={**BODY, "vendor_id": 9, "hours": 4.5, "item": "Huge", "qty": 400}, headers=H(c, "vendor@demo")).json()
    r = c.post("/pickups/plan", json={"ngo_id": 1, "listing_ids": ids + [big["id"]]}, headers=H(c, "ngo@demo"))
    assert r.status_code == 409


def test_TC13_confirm_claims_items_once(c):
    ids = _donations(c, 2)
    h = H(c, "ngo@demo")
    assert c.post("/pickups/confirm", json={"ngo_id": 1, "listing_ids": ids}, headers=h).status_code == 200
    assert c.post("/pickups/plan", json={"ngo_id": 1, "listing_ids": ids}, headers=h).status_code == 404


def test_TC14_impact_cached_and_consistent(c):
    a = c.get("/impact").json(); b = c.get("/impact").json()
    assert a == b and c.get("/health").json()["cache"]["hits"] >= 1
    assert a["co2_net"] <= a["co2_gross"] and a["meals"] >= 0


def test_TC15_surplus_forecast_in_plausible_range(c):
    f = c.post("/forecast/surplus", json=dict(type_of_food="Meat", guests=300, event_type="Wedding", quantity=450, storage="Refrigerated",
                                               purchase="Regular", season="Winter", prep="Buffet", geo="Urban", pricing="Low")).json()
    assert 10 <= f["expected_waste"] <= 63        # observed range in the Kaggle data


def test_TC16_gzip_applied_to_large_response(c):
    for i in range(40):
        c.post("/listings", json={**BODY, "item": f"Bulk item {i}"}, headers=H(c, "vendor@demo"))
    r = c.get("/listings?decision=sell", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_TC17_decide_preview_matches_listing_decision(c):
    p = c.post("/decide", json=dict(category="cooked", storage="hot", temp=30, hours=2, qty_kg=4, mrp=200)).json()
    assert p["decision"] == "sell" and p["source"] == "xgboost" and 20 <= p["discount"] <= 70


def test_TC18_route_endpoint_orders_all_stops(c):
    body = {"depot": {"id": "d", "lat": 12.93, "lng": 77.58}, "stops": [{"id": str(i), "lat": 12.9 + i * 0.01, "lng": 77.6 + (i % 3) * 0.02} for i in range(6)]}
    r = c.post("/route", json=body).json()
    assert sorted(r["order"]) == sorted(str(i) for i in range(6)) and r["km"] <= r["naive_km"] + 1e-6
