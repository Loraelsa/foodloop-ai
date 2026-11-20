"""Pickup routing: haversine x road factor distances, acceptance-order, nearest-neighbour and OR-Tools."""
import math
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

ROAD_FACTOR = 1.3
R_EARTH = 6371.0


def hav(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1]); dp = p2 - p1
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def road(a, b):
    return hav(a, b) * ROAD_FACTOR


def length(depot, pts, order):
    km, cur = 0.0, depot
    for i in order:
        km += road(cur, pts[i]); cur = pts[i]
    return km


def accept_order(depot, pts):
    order = list(range(len(pts)))
    return order, length(depot, pts, order)


def nearest_neighbour(depot, pts):
    left, cur, order = list(range(len(pts))), depot, []
    while left:
        j = min(left, key=lambda i: road(cur, pts[i]))
        order.append(j); left.remove(j); cur = pts[j]
    return order, length(depot, pts, order)


def ortools_route(depot, pts, time_limit_ms=200):
    """Open path from depot through all stops, minimising road distance (guided local search)."""
    n = len(pts)
    if n < 2:
        o = list(range(n)); return o, length(depot, pts, o)
    nodes = [depot] + list(pts)
    N = n + 2                                  # + dummy end node
    D = [[0] * N for _ in range(N)]
    for i in range(n + 1):
        for j in range(n + 1):
            D[i][j] = int(road(nodes[i], nodes[j]) * 1000)
    big = 10 ** 9
    for j in range(n + 1):
        D[n + 1][j] = big
    mgr = pywrapcp.RoutingIndexManager(N, 1, [0], [n + 1])
    r = pywrapcp.RoutingModel(mgr)
    cb = r.RegisterTransitCallback(lambda a, b: D[mgr.IndexToNode(a)][mgr.IndexToNode(b)])
    r.SetArcCostEvaluatorOfAllVehicles(cb)
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromMilliseconds(time_limit_ms)
    sol = r.SolveWithParameters(p)
    if sol is None:
        return nearest_neighbour(depot, pts)
    idx, order = r.Start(0), []
    while not r.IsEnd(idx):
        node = mgr.IndexToNode(idx)
        if 0 < node <= n:
            order.append(node - 1)
        idx = sol.Value(r.NextVar(idx))
    return order, length(depot, pts, order)
