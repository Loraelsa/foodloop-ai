"""Tiny in-process instrumentation: request latency + cache hit-rate (feeds the green-computing evidence)."""
import time
from collections import deque

from cachetools import TTLCache

from .config import IMPACT_CACHE_SECONDS

latencies_ms = deque(maxlen=2000)
cache_stats = {"hits": 0, "misses": 0}
impact_cache: TTLCache = TTLCache(maxsize=8, ttl=IMPACT_CACHE_SECONDS)


def cached(key, producer):
    if key in impact_cache:
        cache_stats["hits"] += 1
        return impact_cache[key]
    cache_stats["misses"] += 1
    value = producer()
    impact_cache[key] = value
    return value


def invalidate():
    impact_cache.clear()


def summary():
    data = sorted(latencies_ms)
    def pct(p):
        return round(data[min(len(data) - 1, int(len(data) * p))], 2) if data else 0.0
    total = cache_stats["hits"] + cache_stats["misses"]
    return {
        "requests_sampled": len(data), "p50_ms": pct(0.5), "p95_ms": pct(0.95),
        "cache_hits": cache_stats["hits"], "cache_misses": cache_stats["misses"],
        "cache_hit_rate": round(cache_stats["hits"] / total, 3) if total else 0.0,
    }


class LatencyMiddleware:
    """Pure-ASGI middleware (cheaper than BaseHTTPMiddleware)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            if scope["path"].startswith("/api"):
                latencies_ms.append((time.perf_counter() - t0) * 1000)
