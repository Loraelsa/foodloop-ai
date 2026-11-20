from app import shelf, routing, impact
import random


def test_U01_temperature_halves_life_every_10C():
    a = shelf.true_life("cooked", "room", 25); b = shelf.true_life("cooked", "room", 35)
    assert abs(b - a / 2) < 1e-9


def test_U02_fridge_extends_life():
    assert shelf.true_life("dairy", "fridge", 8) > shelf.true_life("dairy", "room", 8)


def test_U03_thresholds():
    assert shelf.decide_from_hours(4.0) == "sell" and shelf.decide_from_hours(3.99) == "donate"
    assert shelf.decide_from_hours(1.0) == "donate" and shelf.decide_from_hours(0.99) == "compost"


def test_U04_discount_bounds_and_monotonic():
    assert shelf.discount_pct(4) == 70 and shelf.discount_pct(24) == 20 and shelf.discount_pct(100) == 20
    assert shelf.discount_pct(8) >= shelf.discount_pct(12)


def test_U05_haversine_known_distance():
    # Koramangala to Indiranagar centroids are about 5.3 km apart as the crow flies
    d = routing.hav((12.9352, 77.6245), (12.9784, 77.6408))
    assert 4.5 < d < 6.0


def test_U06_ortools_not_worse_than_acceptance_order():
    random.seed(1)
    depot = (12.93, 77.58)
    for _ in range(5):
        pts = [(12.85 + random.random() * 0.2, 77.5 + random.random() * 0.25) for _ in range(8)]
        _, a = routing.accept_order(depot, pts)
        _, o = routing.ortools_route(depot, pts, 150)
        assert o <= a + 1e-6


def test_U07_impact_formula():
    r = impact.impact(10, 5)
    assert r["meals"] == round(10 / 0.42) and abs(r["co2_net"] - (25 - 5 * 0.2521)) < 0.01
