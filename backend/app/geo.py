"""Spatial helpers: an indexed bounding-box pre-filter followed by an exact great-circle check.

This is what PostGIS ST_DWithin would do; here the (lat, lon) composite index narrows the rows in SQL and haversine
removes the box corners. It works on SQLite and PostgreSQL alike with no extension.
"""
from math import cos, radians

from .routing import haversine_km


def bbox(lat: float, lon: float, radius_km: float):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(cos(radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def within(rows, lat, lon, radius_km):
    return [r for r in rows if haversine_km(lat, lon, r.lat, r.lon) <= radius_km]
