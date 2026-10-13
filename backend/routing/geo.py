"""Small geometry helpers. Coordinates are GeoJSON order: [lon, lat]."""
from __future__ import annotations

import math

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_mi(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(coords: list) -> list[float]:
    out = [0.0]
    for i in range(1, len(coords)):
        out.append(out[-1] + haversine_mi(coords[i - 1], coords[i]))
    return out


def interpolate_at(coords: list, cum: list[float], target: float, values: list[float] | None = None):
    """Point (lon, lat) at `target` miles along the line; optionally also interpolate `values`."""
    if target <= 0:
        idx, t = 0, 0.0
    elif target >= cum[-1]:
        idx, t = len(cum) - 2, 1.0
    else:
        lo, hi = 0, len(cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if cum[mid] <= target:
                lo = mid
            else:
                hi = mid
        idx = lo
        seg = cum[idx + 1] - cum[idx]
        t = (target - cum[idx]) / seg if seg else 0.0
    a, b = coords[idx], coords[idx + 1]
    point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    if values is None:
        return point
    return point, values[idx] + (values[idx + 1] - values[idx]) * t


def bearing(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return math.atan2(y, x)


def offset_point(point, bearing_rad: float, miles: float):
    lon, lat = math.radians(point[0]), math.radians(point[1])
    d = miles / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat) * math.cos(d) + math.cos(lat) * math.sin(d) * math.cos(bearing_rad))
    lon2 = lon + math.atan2(math.sin(bearing_rad) * math.sin(d) * math.cos(lat),
                            math.cos(d) - math.sin(lat) * math.sin(lat2))
    return (math.degrees(lon2), math.degrees(lat2))


def decimate(coords: list, max_points: int = 800) -> list:
    """Uniformly thin a polyline for transport/rendering (keeps first and last)."""
    if len(coords) <= max_points:
        return coords
    step = (len(coords) - 1) / (max_points - 1)
    return [coords[round(i * step)] for i in range(max_points)]


def overlap_fraction(a: list, b: list, tol_mi: float = 2.0) -> float:
    """Fraction of (sampled) points of b that lie within tol_mi of polyline a's vertices."""
    a_s = decimate(a, 400)
    b_s = decimate(b, 25)
    close = 0
    for p in b_s:
        if min(haversine_mi(p, q) for q in a_s) <= tol_mi:
            close += 1
    return close / len(b_s)
