"""Sliding-window rate limiter (per client IP, in memory). Enough for one container; use Redis if you scale out."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from . import config

_hits: dict = defaultdict(deque)


def _check(key: str, limit: int, window_s: int = 60):
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests - please wait a minute and try again",
                            headers={"Retry-After": str(window_s)})
    q.append(now)


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def limit_api(request: Request):
    _check(f"api:{_ip(request)}", config.RATE_LIMIT_API)


def limit_auth(request: Request):
    _check(f"auth:{_ip(request)}", config.RATE_LIMIT_AUTH)


def reset():
    _hits.clear()
