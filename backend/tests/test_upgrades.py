import io

import pytest
from PIL import Image

from app import ratelimit
from app.api_extra import calibrate_margin
from app.routing import distance_matrix, plan_route

from .conftest import admin_headers, make_user
from .test_api import FRESH, MID


def png_bytes(size=(64, 48)):
    b = io.BytesIO(); Image.new("RGB", size, (200, 30, 30)).save(b, "PNG"); return b.getvalue()


def test_TC13_unverified_vendor_and_ngo_are_blocked_until_admin_approves(client):
    vh, v = make_user(client, "vendor", verified=False)
    assert client.post("/api/listings", json=FRESH, headers=vh).status_code == 403
    assert client.post("/api/predict", json=FRESH, headers=vh).status_code == 200      # preview still allowed
    nh, n = make_user(client, "ngo", verified=False)
    assert client.post("/api/ngo/accept", json={"listing_ids": [1]}, headers=nh).status_code == 403
    ah = admin_headers(client)
    assert {u["id"] for u in client.get("/api/admin/pending", headers=ah).json()} >= {v["id"], n["id"]}
    assert client.post(f"/api/admin/users/{v['id']}/verify", json={"approve": True}, headers=ah).status_code == 200
    assert client.post("/api/listings", json=FRESH, headers=vh).status_code == 201


def test_TC14_admin_endpoints_are_admin_only(client):
    h, _ = make_user(client, "vendor")
    assert client.get("/api/admin/pending", headers=h).status_code == 403


def test_TC15_donation_notifies_nearby_verified_ngo_only(client):
    near, nn = make_user(client, "ngo", lat=28.61, lon=77.21)
    far, _ = make_user(client, "ngo", lat=19.07, lon=72.87)           # Mumbai
    vh, _ = make_user(client, "vendor", lat=28.62, lon=77.20)
    lid = client.post("/api/listings", json=MID, headers=vh).json()["id"]
    got = client.get("/api/notifications", headers=near).json()
    assert got["unread"] >= 1 and any(i["listing_id"] == lid for i in got["items"])
    assert not any(i["listing_id"] == lid for i in client.get("/api/notifications", headers=far).json()["items"])
    client.post("/api/notifications/read", headers=near)
    assert client.get("/api/notifications", headers=near).json()["unread"] == 0


def test_TC16_radius_filter_uses_distance(client):
    vh, _ = make_user(client, "vendor", lat=28.70, lon=77.10)
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    ch, _ = make_user(client, "citizen", lat=28.61, lon=77.21)          # about 14 km away
    assert any(x["id"] == lid for x in client.get("/api/market?radius_km=30", headers=ch).json())
    assert not any(x["id"] == lid for x in client.get("/api/market?radius_km=5", headers=ch).json())


def test_TC17_photo_upload_validates_and_serves(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    ok = client.post(f"/api/listings/{lid}/photo", files={"file": ("a.png", png_bytes(), "image/png")}, headers=vh)
    assert ok.status_code == 200
    r = client.get(f"/api/listings/{lid}/photo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    bad = client.post(f"/api/listings/{lid}/photo", files={"file": ("a.png", b"<script>alert(1)</script>", "image/png")}, headers=vh)
    assert bad.status_code == 415                                        # content sniffed, not filename trusted
    other, _ = make_user(client, "vendor")
    assert client.post(f"/api/listings/{lid}/photo", files={"file": ("a.png", png_bytes(), "image/png")}, headers=other).status_code == 404


def test_TC18_qr_handover_completes_sale_only_with_right_code(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    ch, _ = make_user(client, "citizen")
    assert client.get(f"/api/listings/{lid}/qr", headers=ch).status_code == 404   # not reserved yet
    client.post(f"/api/listings/{lid}/reserve", headers=ch)
    q = client.get(f"/api/listings/{lid}/qr", headers=ch).json()
    assert "<svg" in q["svg"] and len(q["code"]) == 8
    other, _ = make_user(client, "citizen")
    assert client.get(f"/api/listings/{lid}/qr", headers=other).status_code == 404  # someone else's code
    assert client.post("/api/handover", json={"code": "WRONGCODE"}, headers=vh).status_code == 404
    r = client.post("/api/handover", json={"code": q["code"].lower()}, headers=vh)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert client.post("/api/handover", json={"code": q["code"]}, headers=vh).status_code == 409


def test_TC19_ngo_handover_closes_pickup(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=MID, headers=vh).json()["id"]
    nh, _ = make_user(client, "ngo")
    pid = client.post("/api/ngo/accept", json={"listing_ids": [lid]}, headers=nh).json()["id"]
    code = next(i for i in client.get("/api/my/items", headers=nh).json() if i["id"] == lid)["pickup_code"]
    client.post("/api/handover", json={"code": code}, headers=vh)
    assert next(p for p in client.get("/api/ngo/pickups", headers=nh).json() if p["id"] == pid)["status"] == "completed"


def test_TC20_outcome_reporting_rules(client):
    vh, _ = make_user(client, "vendor")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    ch, _ = make_user(client, "citizen")
    client.post(f"/api/listings/{lid}/reserve", headers=ch)
    assert client.post(f"/api/listings/{lid}/outcome", json={"verdict": "fine"}, headers=ch).status_code == 409  # not handed over
    client.post(f"/api/listings/{lid}/complete", headers=vh)
    assert client.post(f"/api/listings/{lid}/outcome", json={"verdict": "spoiled"}, headers=ch).status_code == 201
    assert client.post(f"/api/listings/{lid}/outcome", json={"verdict": "fine"}, headers=ch).status_code == 409   # once only
    stranger, _ = make_user(client, "citizen")
    assert client.post(f"/api/listings/{lid}/outcome", json={"verdict": "fine"}, headers=stranger).status_code == 403
    csv = client.get("/api/admin/outcomes.csv", headers=admin_headers(client)).text
    assert csv.splitlines()[0].startswith("listing_id") and f"\n{lid}," in csv


def test_TC21_calibration_picks_smallest_margin_that_meets_target():
    assert calibrate_margin([(5.0, False)] * 10)["status"] == "insufficient_data"
    # 40 items predicted 1.0-1.9 h left: all spoiled; 60 items predicted 6 h: all fine
    pairs = [(1.5, True)] * 40 + [(6.0, False)] * 60
    res = calibrate_margin(pairs, target=0.05)
    assert res["status"] == "ok" and res["recommended_margin_h"] >= 0.75   # a margin > 0.5 removes the 1.5 h group
    assert res["table"][0]["spoiled_rate"] == pytest.approx(0.4)


def test_TC22_admin_calibrate_applies_margin_to_engine(client):
    from app.ml import engine
    ah = admin_headers(client)
    assert client.post("/api/admin/calibrate", headers=ah).json()["status"] in ("insufficient_data", "ok")
    engine.set_margin(0.0)


def test_TC23_rate_limiter_blocks_after_limit():
    ratelimit.reset()
    for _ in range(3):
        ratelimit._check("t", 3)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        ratelimit._check("t", 3)
    assert e.value.status_code == 429
    ratelimit.reset()


def test_TC24_route_falls_back_to_haversine_when_osrm_off_and_uses_osrm_when_on(monkeypatch):
    from app import config, routing
    pts = [(28.61, 77.20), (28.64, 77.23), (28.58, 77.25)]
    m, src = distance_matrix(pts)
    assert src == "haversine" and m[0][1] > 0
    fake = [[0, 1000, 2000], [1000, 0, 1500], [2000, 1500, 0]]
    monkeypatch.setattr(config, "OSRM_URL", "http://osrm.test")
    monkeypatch.setattr(routing, "_osrm_matrix", lambda p: fake)
    routing._matrix_cache.clear()
    m2, src2 = distance_matrix(pts)
    assert src2 == "osrm" and m2 == fake
    plan = plan_route((28.61, 77.20), [{"id": 1, "lat": 28.64, "lon": 77.23, "kg": 3, "name": "a"},
                                       {"id": 2, "lat": 28.58, "lon": 77.25, "kg": 3, "name": "b"}])
    assert plan["distance_source"] == "osrm"
    routing._matrix_cache.clear()


def _completed_order(client):
    vh, _ = make_user(client, "vendor", lat=28.62, lon=77.20)
    ch, c = make_user(client, "citizen")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    assert client.post(f"/api/listings/{lid}/reserve", headers=ch).status_code == 200
    assert client.post(f"/api/listings/{lid}/complete", headers=vh).status_code == 200
    return vh, ch, lid


def test_TC25_rating_needs_a_collected_order_and_feeds_the_market(client):
    vh, _ = make_user(client, "vendor", lat=28.62, lon=77.20)
    ch, _ = make_user(client, "citizen")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    client.post(f"/api/listings/{lid}/reserve", headers=ch)
    assert client.post(f"/api/listings/{lid}/review", json={"stars": 5}, headers=ch).status_code == 409   # not collected yet
    client.post(f"/api/listings/{lid}/complete", headers=vh)
    assert client.post(f"/api/listings/{lid}/review", json={"stars": 6}, headers=ch).status_code == 422
    assert client.post(f"/api/listings/{lid}/review", json={"stars": 4, "comment": "Fresh"}, headers=ch).status_code == 201
    assert client.post(f"/api/listings/{lid}/review", json={"stars": 4}, headers=ch).status_code == 409   # only once
    other, _ = make_user(client, "citizen")
    assert client.post(f"/api/listings/{lid}/review", json={"stars": 1}, headers=other).status_code == 404  # not their order
    again = client.post("/api/listings", json=FRESH, headers=vh).json()
    row = next(x for x in client.get("/api/market", headers=ch).json() if x["id"] == again["id"])
    assert row["vendor_rating"] == 4.0 and row["vendor_reviews"] == 1


def test_TC26_complaint_lifecycle(client):
    vh, ch, lid = _completed_order(client)
    ah = admin_headers(client)
    r = client.post("/api/complaints", json={"topic": "food_quality", "message": "The rice smelled sour.", "listing_id": lid}, headers=ch)
    assert r.status_code == 201 and r.json()["status"] == "open"
    cid = r.json()["id"]
    stranger, _ = make_user(client, "citizen")
    assert client.post("/api/complaints", json={"topic": "other", "message": "Not my order at all", "listing_id": lid}, headers=stranger).status_code == 403
    assert client.post("/api/complaints", json={"topic": "bogus", "message": "Invalid topic here"}, headers=ch).status_code == 422
    assert client.get("/api/admin/complaints", headers=ch).status_code == 403
    assert cid in [c["id"] for c in client.get("/api/admin/complaints", headers=ah).json()]
    assert client.post(f"/api/admin/complaints/{cid}/reply", json={"status": "resolved", "response": "Refund agreed with the vendor."}, headers=ah).status_code == 200
    mine = client.get("/api/complaints/mine", headers=ch).json()
    assert mine[0]["status"] == "resolved" and "Refund" in mine[0]["response"]
    assert any(n["kind"] == "complaint" for n in client.get("/api/notifications", headers=ch).json()["items"])


def test_TC27_cancel_reservation_releases_item_and_changes_code(client):
    vh, _ = make_user(client, "vendor", lat=28.62, lon=77.20)
    ch, _ = make_user(client, "citizen")
    lid = client.post("/api/listings", json=FRESH, headers=vh).json()["id"]
    client.post(f"/api/listings/{lid}/reserve", headers=ch)
    old = client.get(f"/api/listings/{lid}/qr", headers=ch).json()["code"]
    assert client.post(f"/api/listings/{lid}/cancel", headers=ch).status_code == 200
    assert lid in [x["id"] for x in client.get("/api/market", headers=ch).json()]
    other, _ = make_user(client, "citizen")
    client.post(f"/api/listings/{lid}/reserve", headers=other)
    assert client.get(f"/api/listings/{lid}/qr", headers=other).json()["code"] != old
    assert client.post(f"/api/listings/{lid}/cancel", headers=ch).status_code == 409   # no longer theirs
