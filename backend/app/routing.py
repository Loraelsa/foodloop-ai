"""NGO pickup routing with Google OR-Tools (capacitated VRP) + emissions estimate."""
import json
import urllib.request
from math import asin, cos, radians, sin, sqrt

from cachetools import TTLCache
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from . import config
from .config import EMISSION_KG_PER_KM, ROAD_FACTOR

_matrix_cache: TTLCache = TTLCache(maxsize=64, ttl=600)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dphi, dl = p2 - p1, radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _haversine_matrix(points):
    n = len(points)
    return [[int(haversine_km(*points[i], *points[j]) * ROAD_FACTOR * 1000) for j in range(n)] for i in range(n)]


def _osrm_matrix(points):
    """Road distances in metres from an OSRM /table call, or None if the service is off/unreachable."""
    if not config.OSRM_URL or len(points) > 90:
        return None
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in points)
    url = f"{config.OSRM_URL.rstrip('/')}/table/v1/driving/{coords}?annotations=distance"
    try:
        with urllib.request.urlopen(url, timeout=config.OSRM_TIMEOUT_S) as r:
            data = json.loads(r.read())
        d = data.get("distances")
        if data.get("code") != "Ok" or not d or any(v is None for row in d for v in row):
            return None
        return [[int(v) for v in row] for row in d]
    except Exception:  # network error, timeout, bad JSON: fall back silently, the route is still valid
        return None


def distance_matrix(points):
    """Returns (matrix_in_metres, source) where source is 'osrm' (road network) or 'haversine' (estimate)."""
    key = tuple((round(a, 5), round(b, 5)) for a, b in points)
    if key in _matrix_cache:
        return _matrix_cache[key]
    m = _osrm_matrix(points)
    out = (m, "osrm") if m else (_haversine_matrix(points), "haversine")
    _matrix_cache[key] = out
    return out


def route_length_m(order, m):
    return sum(m[a][b] for a, b in zip(order, order[1:]))


def plan_route(depot, stops, vehicles=1, capacity_kg=None, time_limit_ms=1000):
    """depot=(lat,lon). stops=[{id,lat,lon,kg,name}]. Returns ordered routes and distance stats.

    Baseline = visiting stops in the order the NGO accepted them (what a manual dispatcher would do).
    """
    if not stops:
        return {"routes": [], "distance_km": 0.0, "baseline_km": 0.0, "saved_km": 0.0, "co2_saved_kg": 0.0}
    points = [depot] + [(s["lat"], s["lon"]) for s in stops]
    m, source = distance_matrix(points)
    n = len(points)

    baseline_order = list(range(n)) + [0]
    baseline_m = route_length_m(baseline_order, m)

    manager = pywrapcp.RoutingIndexManager(n, vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)
    transit = routing.RegisterTransitCallback(lambda i, j: m[manager.IndexToNode(i)][manager.IndexToNode(j)])
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    if capacity_kg:
        demands = [0] + [int(round(s["kg"] * 10)) for s in stops]  # tenths of kg -> ints
        d_idx = routing.RegisterUnaryTransitCallback(lambda i: demands[manager.IndexToNode(i)])
        routing.AddDimensionWithVehicleCapacity(d_idx, 0, [int(capacity_kg * 10)] * vehicles, True, "Load")

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(time_limit_ms)
    sol = routing.SolveWithParameters(params)

    if sol is None:  # infeasible (e.g. capacity too small) -> fall back to baseline order, flagged
        order_nodes = [baseline_order]
        opt_m = baseline_m
        feasible = False
    else:
        feasible = True
        order_nodes, opt_m = [], 0
        for v in range(vehicles):
            idx, seq = routing.Start(v), []
            while not routing.IsEnd(idx):
                seq.append(manager.IndexToNode(idx))
                idx = sol.Value(routing.NextVar(idx))
            seq.append(0)
            if len(seq) > 2:
                order_nodes.append(seq)
                opt_m += route_length_m(seq, m)

    routes = []
    for seq in order_nodes:
        routes.append([
            {"seq": k, "listing_id": None if node == 0 else stops[node - 1]["id"],
             "name": "NGO depot" if node == 0 else stops[node - 1]["name"],
             "lat": points[node][0], "lon": points[node][1]}
            for k, node in enumerate(seq)
        ])
    opt_km, base_km = opt_m / 1000, baseline_m / 1000
    saved = max(0.0, base_km - opt_km)
    return {
        "routes": routes, "distance_km": round(opt_km, 2), "baseline_km": round(base_km, 2),
        "saved_km": round(saved, 2), "co2_saved_kg": round(saved * EMISSION_KG_PER_KM, 3),
        "feasible": feasible, "distance_source": source,
    }
