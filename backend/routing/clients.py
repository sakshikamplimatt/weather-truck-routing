"""Thin clients for third-party APIs: Nominatim (geocode), OSRM (routes), Open-Meteo (weather).

All three are free and need no API key.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import requests
from django.core.cache import cache

from . import geo

USER_AGENT = "weather-aware-truck-routing/1.0 (demo app)"
TIMEOUT = 25
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class UpstreamError(Exception):
    """A third-party API failed or returned something unusable."""


def _get(url: str, params: dict | None = None) -> dict | list:
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise UpstreamError(f"{url.split('/')[2]} request failed: {exc}") from exc


# --------------------------------------------------------------------------- geocoding
def geocode(query: str, limit: int = 5) -> list[dict]:
    key = f"geo:{query.strip().lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = _get(NOMINATIM_URL, {"q": query, "format": "jsonv2", "limit": limit, "countrycodes": "us,ca,mx"})
    results = [{"label": d["display_name"], "lat": float(d["lat"]), "lon": float(d["lon"])} for d in data]
    cache.set(key, results, 24 * 3600)
    return results


# --------------------------------------------------------------------------- routing
def _osrm(points: list[tuple[float, float]], alternatives: bool) -> list[dict]:
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    data = _get(f"{OSRM_URL}/{coords}", {
        "alternatives": "3" if alternatives else "false",
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration",
        "steps": "false",
    })
    if data.get("code") != "Ok":
        raise UpstreamError(f"OSRM: {data.get('message') or data.get('code')}")
    routes = []
    for r in data["routes"]:
        coords_ll = r["geometry"]["coordinates"]
        # per-edge durations (seconds) aligned with consecutive coordinates
        durations = []
        for leg in r["legs"]:
            durations.extend(leg.get("annotation", {}).get("duration", []))
        routes.append({
            "coords": coords_ll,
            "distance_m": r["distance"],
            "duration_s": r["duration"],
            "edge_durations": durations if len(durations) == len(coords_ll) - 1 else None,
        })
    return routes


def get_routes(origin: tuple[float, float], dest: tuple[float, float], want: int = 3) -> list[dict]:
    """Return up to `want` distinct driving routes between (lon, lat) points.

    Uses OSRM's native alternatives first. If it returns fewer than `want`, synthesises
    extra candidates by routing through a via-point offset to either side of the
    midpoint, keeping only those that differ meaningfully from routes already found.
    """
    routes = _osrm([origin, dest], alternatives=True)

    def is_new(candidate: dict) -> bool:
        return all(geo.overlap_fraction(r["coords"], candidate["coords"]) < 0.85 for r in routes)

    if len(routes) < want:
        base = routes[0]["coords"]
        cum = geo.cumulative_miles(base)
        total = cum[-1]
        mid = geo.interpolate_at(base, cum, total / 2)
        brg = geo.bearing(base[0], base[-1])
        # Larger detours for longer trips, but never silly ones.
        offsets = [max(8.0, min(total * 0.18, 120.0)) * k for k in (1, -1, 2, -2)]
        for off in offsets:
            if len(routes) >= want:
                break
            via = geo.offset_point(mid, brg + math.pi / 2, off)
            try:
                cand = _osrm([origin, via, dest], alternatives=False)[0]
            except UpstreamError:
                continue
            if is_new(cand) and cand["duration_s"] < routes[0]["duration_s"] * 2.0:
                routes.append(cand)
    return routes[:want]


# --------------------------------------------------------------------------- weather
HOURLY_VARS = "wind_speed_10m,rain,snowfall"


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def fetch_hourly(points: list[tuple[float, float]], start: datetime, end: datetime) -> dict:
    """Hourly forecast (UTC) for many (lat, lon) points between start and end.

    Returns {(lat, lon): {"t0": datetime, "wind": [mph...], "rain": [in/hr...], "snow": [in/hr...]}}.
    Coordinates are rounded to 2 decimals (~0.7 mi), which also dedupes nearby checkpoints
    and makes the 15-minute cache effective.
    """
    s_date = start.astimezone(timezone.utc).date()
    e_date = (end.astimezone(timezone.utc) + timedelta(hours=1)).date()
    out: dict = {}
    todo = []
    for p in {(round(lat, 2), round(lon, 2)) for lat, lon in points}:
        hit = cache.get(f"wx:{p}:{s_date}:{e_date}")
        if hit is not None:
            out[p] = hit
        else:
            todo.append(p)

    for chunk in _chunks(todo, 50):
        data = _get(OPEN_METEO_URL, {
            "latitude": ",".join(str(p[0]) for p in chunk),
            "longitude": ",".join(str(p[1]) for p in chunk),
            "hourly": HOURLY_VARS,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "UTC",
            "start_date": s_date.isoformat(),
            "end_date": e_date.isoformat(),
        })
        items = data if isinstance(data, list) else [data]
        if len(items) != len(chunk):
            raise UpstreamError("Open-Meteo returned an unexpected number of locations")
        for p, item in zip(chunk, items):
            h = item["hourly"]
            t0 = datetime.fromisoformat(h["time"][0]).replace(tzinfo=timezone.utc)
            series = {
                "t0": t0,
                "wind": [v or 0.0 for v in h["wind_speed_10m"]],
                "rain": [v or 0.0 for v in h["rain"]],
                "snow": [v or 0.0 for v in h["snowfall"]],
            }
            cache.set(f"wx:{p}:{s_date}:{e_date}", series, 15 * 60)
            out[p] = series
    return out


def weather_at(series: dict, when: datetime) -> tuple[float, float, float, bool]:
    """(wind_mph, rain_in_hr, snow_in_hr, clamped) at `when`, using the nearest forecast hour."""
    idx = round((when.astimezone(timezone.utc) - series["t0"]).total_seconds() / 3600)
    last = len(series["wind"]) - 1
    clamped = idx < 0 or idx > last
    idx = max(0, min(last, idx))
    return series["wind"][idx], series["rain"][idx], series["snow"][idx], clamped
