"""Orchestrates routes + weather + risk into the /api/plan response."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import clients, geo, risk

VALID_INTERVALS = (10, 25, 50)
MAX_LOOKAHEAD = timedelta(days=14)
HEATMAP_SPACING_MI = 30
HEATMAP_LATERAL_MI = 20
HEATMAP_HOURS = 48
HEATMAP_MAX_POINTS = 300


class ValidationError(ValueError):
    pass


def validate_request(body: dict) -> dict:
    try:
        o, d = body["origin"], body["destination"]
        origin = (float(o["lon"]), float(o["lat"]))
        dest = (float(d["lon"]), float(d["lat"]))
        load_lb = float(body["load_lb"])
        departure = datetime.fromisoformat(str(body["departure"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid or missing field: {exc}") from exc
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)
    interval = int(body.get("interval_miles", 25))
    if interval not in VALID_INTERVALS:
        raise ValidationError(f"interval_miles must be one of {VALID_INTERVALS}")
    if not (0 < load_lb <= 100_000):
        raise ValidationError("load_lb must be between 1 and 100,000")
    now = datetime.now(timezone.utc)
    if departure < now - timedelta(hours=6) or departure > now + MAX_LOOKAHEAD:
        raise ValidationError("Departure must be within the forecast window (up to 14 days ahead).")
    return {"origin": origin, "dest": dest, "load_lb": load_lb, "departure": departure, "interval": interval}


def _time_at(cum_mi: list[float], cum_s: list[float] | None, total_s: float, miles: float) -> float:
    """Seconds elapsed at `miles` along the route."""
    if cum_s is None:  # fall back to constant average speed
        return total_s * (miles / cum_mi[-1]) if cum_mi[-1] else 0.0
    # cum_s is aligned with cum_mi (same vertices) -> reuse interpolation helper
    return geo.interpolate_at([(m, 0.0) for m in cum_mi], cum_mi, miles, cum_s)[1]


def _build_route(raw: dict, interval: int) -> dict:
    coords = raw["coords"]
    cum_mi = geo.cumulative_miles(coords)
    # scale haversine miles to the router's road distance (haversine slightly underestimates)
    total_mi = raw["distance_m"] / geo.METERS_PER_MILE
    scale = total_mi / cum_mi[-1] if cum_mi[-1] else 1.0
    cum_mi = [m * scale for m in cum_mi]

    cum_s = None
    if raw["edge_durations"]:
        cum_s = [0.0]
        for dsec in raw["edge_durations"]:
            cum_s.append(cum_s[-1] + dsec)

    distances = [float(m) for m in range(0, int(total_mi), interval)]
    if not distances or total_mi - distances[-1] > 1e-6:
        distances.append(total_mi)  # always sample the destination
    checkpoints = []
    for d in distances:
        lon, lat = geo.interpolate_at(coords, cum_mi, d)
        elapsed = _time_at(cum_mi, cum_s, raw["duration_s"], d)
        checkpoints.append({"mile": round(d, 1), "lat": lat, "lon": lon, "elapsed_s": elapsed})
    return {
        "coords": coords,
        "distance_mi": round(total_mi, 1),
        "duration_s": raw["duration_s"],
        "checkpoints": checkpoints,
    }


def plan(body: dict) -> dict:
    req = validate_request(body)
    raw_routes = clients.get_routes(req["origin"], req["dest"], want=3)
    routes = [_build_route(r, req["interval"]) for r in raw_routes]

    # one batched weather fetch for every checkpoint of every route
    all_pts = [(c["lat"], c["lon"]) for r in routes for c in r["checkpoints"]]
    last_eta = req["departure"] + timedelta(seconds=max(r["duration_s"] for r in routes))
    series = clients.fetch_hourly(all_pts, req["departure"], last_eta)

    clamped_any = False
    for r in routes:
        levels = []
        for c in r["checkpoints"]:
            eta = req["departure"] + timedelta(seconds=c["elapsed_s"])
            s = series[(round(c["lat"], 2), round(c["lon"], 2))]
            wind, rain, snow, clamped = clients.weather_at(s, eta)
            clamped_any |= clamped
            a = risk.assess(wind, rain, snow, req["load_lb"])
            c.update({
                "eta": eta.isoformat(),
                "wind_mph": round(wind, 1),
                "rain_in_hr": round(rain, 3),
                "snow_in_hr": round(snow, 3),
                **a.as_dict(),
            })
            levels.append(a.level)
        r["summary"] = risk.summarize(levels, [c["mile"] for c in r["checkpoints"]], r["distance_mi"])
        r["arrival"] = (req["departure"] + timedelta(seconds=r["duration_s"])).isoformat()

    best, why = risk.recommend(routes)
    for i, r in enumerate(routes):
        r["id"] = i
        r["recommended"] = i == best
        r["geometry"] = geo.decimate(r.pop("coords"), 900)

    return {
        "routes": routes,
        "recommended_index": best,
        "recommendation_reason": why,
        "interval_miles": req["interval"],
        "departure": req["departure"].isoformat(),
        "load_lb": req["load_lb"],
        "forecast_clamped": clamped_any,
        "notes": [
            "Routing uses the OSRM car profile (no truck restrictions).",
            "Weather is the Open-Meteo hourly forecast at the nearest hour to each ETA.",
        ] + (["Some arrivals fall outside the available forecast; the nearest available hour was used."] if clamped_any else []),
        "heatmap_points": heatmap_points(routes),
    }


def heatmap_points(routes: list[dict]) -> list[dict]:
    """Corridor sample points: along every route every ~30 mi, plus a cross-track pair either side."""
    seen: set = set()
    pts: list[dict] = []
    for r in routes:
        geom = r["geometry"]
        cum = geo.cumulative_miles(geom)
        d = 0.0
        while d <= cum[-1] and len(pts) < HEATMAP_MAX_POINTS:
            lon, lat = geo.interpolate_at(geom, cum, d)
            j = geo.interpolate_at(geom, cum, min(d + 2, cum[-1]))
            brg = geo.bearing((lon, lat), j) if d < cum[-1] else 0.0
            for off in (0, HEATMAP_LATERAL_MI, -HEATMAP_LATERAL_MI):
                p = (lon, lat) if off == 0 else geo.offset_point((lon, lat), brg + 1.5708, off)
                key = (round(p[1], 1), round(p[0], 1))
                if key not in seen and len(pts) < HEATMAP_MAX_POINTS:
                    seen.add(key)
                    pts.append({"lat": round(p[1], 3), "lon": round(p[0], 3)})
            d += HEATMAP_SPACING_MI
    return pts


def heatmap(points: list[dict], load_lb: float) -> dict:
    """Risk level per point for each of the next 0..48 hours (hour 0 = current hour, UTC)."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now + timedelta(hours=HEATMAP_HOURS)
    pts = [(p["lat"], p["lon"]) for p in points[:HEATMAP_MAX_POINTS]]
    series = clients.fetch_hourly(pts, now, end)
    out = []
    for lat, lon in pts:
        s = series[(round(lat, 2), round(lon, 2))]
        levels = []
        for h in range(HEATMAP_HOURS + 1):
            wind, rain, snow, _ = clients.weather_at(s, now + timedelta(hours=h))
            levels.append(risk.assess(wind, rain, snow, load_lb).level)
        out.append({"lat": lat, "lon": lon, "levels": levels})
    return {"start": now.isoformat(), "hours": HEATMAP_HOURS, "points": out}
