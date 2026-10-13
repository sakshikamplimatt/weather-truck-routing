"""Weather risk classification, load rules and route ranking.

Pure Python (no Django, no network) so it is trivially unit-testable.

Threshold interpretation
------------------------
The spec's ranges overlap or leave gaps at their edges (e.g. rain "0.10-0.25"
and "0.25-0.50"), so every band uses an inclusive LOWER bound:

    Wind  : <25 Low | 25-<35 Moderate | 35-<45 High | 45-<55 Severe | >=55 No Travel
    Rain  : <0.10 Low | 0.10-<0.25 Moderate | 0.25-<0.50 High | 0.50-1.00 Severe | >1.00 No Travel
    Snow  : <0.5 Low | 0.5-<1.0 Moderate | 1.0-<2.0 High | 2.0-3.0 Severe | >3.0 No Travel

Wind "No Travel" is inclusive (>=55); rain/snow "No Travel" is strict (>1.00 / >3.0),
exactly as written in the spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = range(5)
LEVEL_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"]

# (moderate_from, high_from, severe_from, no_travel_threshold, no_travel_inclusive)
_BANDS = {
    "wind": (25.0, 35.0, 45.0, 55.0, True),
    "rain": (0.10, 0.25, 0.50, 1.00, False),
    "snow": (0.5, 1.0, 2.0, 3.0, False),
}

# Load rules (lb)
HEAVY_SEVERE_WIND_LOAD = 30_000   # 45-54 mph and load > this  -> No Travel
HEAVY_HIGH_WIND_LOAD = 40_000     # 35-44 mph and load > this  -> Severe

# Ranking tolerances: sampling every 10-50 miles makes sub-mile differences noise.
MILES_BUCKET = 1.0
AVG_RISK_BUCKET = 0.05


def classify(kind: str, value: float) -> int:
    """Risk level (0-4) for a single weather quantity, ignoring load."""
    moderate, high, severe, nt, nt_inclusive = _BANDS[kind]
    if (value >= nt) if nt_inclusive else (value > nt):
        return NO_TRAVEL
    if value >= severe:
        return SEVERE
    if value >= high:
        return HIGH
    if value >= moderate:
        return MODERATE
    return LOW


def apply_load_rules(wind_mph: float, load_lb: float, level: int) -> tuple[int, str | None]:
    """Escalate `level` per the load rules. Returns (new_level, reason|None)."""
    if wind_mph >= 55:
        return NO_TRAVEL, "Wind >= 55 mph: no travel for any load"
    if 45 <= wind_mph < 55 and load_lb > HEAVY_SEVERE_WIND_LOAD:
        return NO_TRAVEL, f"Wind 45-54 mph with load > {HEAVY_SEVERE_WIND_LOAD:,} lb: no travel"
    if 35 <= wind_mph < 45 and load_lb > HEAVY_HIGH_WIND_LOAD and level < SEVERE:
        return SEVERE, f"Wind 35-44 mph with load > {HEAVY_HIGH_WIND_LOAD:,} lb: severe"
    return level, None


@dataclass
class Assessment:
    level: int
    wind_level: int
    rain_level: int
    snow_level: int
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return LEVEL_NAMES[self.level]

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "label": self.label,
            "wind_level": self.wind_level,
            "rain_level": self.rain_level,
            "snow_level": self.snow_level,
            "reasons": self.reasons,
        }


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk at one checkpoint: worst of wind/rain/snow, then load rules."""
    w = classify("wind", wind_mph)
    r = classify("rain", rain_in_hr)
    s = classify("snow", snow_in_hr)
    level = max(w, r, s)
    reasons = []
    for name, lv, val, unit in (("Wind", w, wind_mph, "mph"), ("Rain", r, rain_in_hr, "in/hr"), ("Snow", s, snow_in_hr, "in/hr")):
        if lv >= MODERATE:
            reasons.append(f"{name} {val:.2f} {unit}: {LEVEL_NAMES[lv]}")
    level, load_reason = apply_load_rules(wind_mph, load_lb, level)
    if load_reason:
        reasons.append(load_reason)
    return Assessment(level, w, r, s, reasons)


def segment_miles(distances: Sequence[float], total: float) -> list[float]:
    """Miles of route 'owned' by each checkpoint (midpoint to midpoint)."""
    n = len(distances)
    out = []
    for i, d in enumerate(distances):
        start = 0.0 if i == 0 else (distances[i - 1] + d) / 2
        end = total if i == n - 1 else (d + distances[i + 1]) / 2
        out.append(max(0.0, end - start))
    return out


def summarize(levels: Iterable[int], distances: Sequence[float], total_miles: float) -> dict:
    """Mile-weighted risk summary for one route."""
    levels = list(levels)
    seg = segment_miles(distances, total_miles)
    by_level = [0.0] * 5
    for lv, m in zip(levels, seg):
        by_level[lv] += m
    covered = sum(seg) or 1.0
    avg = sum(lv * m for lv, m in zip(levels, seg)) / covered
    return {
        "miles_by_level": {LEVEL_NAMES[i]: round(by_level[i], 1) for i in range(5)},
        "no_travel_miles": round(by_level[NO_TRAVEL], 1),
        "severe_miles": round(by_level[SEVERE], 1),
        "high_miles": round(by_level[HIGH], 1),
        "avg_risk": round(avg, 3),
        "max_level": max(levels) if levels else LOW,
        "max_label": LEVEL_NAMES[max(levels)] if levels else LEVEL_NAMES[LOW],
    }


def ranking_key(summary: dict, duration_s: float) -> tuple:
    """Lower is better.

    Order: No-Travel miles (strictly worse than Severe) -> Severe miles ->
    High miles -> average risk -> travel time.
    """
    def bucket(x: float, size: float) -> int:
        return int(round(x / size))

    return (
        bucket(summary["no_travel_miles"], MILES_BUCKET),
        bucket(summary["severe_miles"], MILES_BUCKET),
        bucket(summary["high_miles"], MILES_BUCKET),
        bucket(summary["avg_risk"], AVG_RISK_BUCKET),
        duration_s,
    )


def recommend(routes: list[dict]) -> tuple[int, str]:
    """Pick the best route. Each route needs 'summary' and 'duration_s'.

    Returns (index, human explanation).
    """
    keys = [ranking_key(r["summary"], r["duration_s"]) for r in routes]
    best = min(range(len(routes)), key=lambda i: keys[i])
    b = routes[best]["summary"]
    if b["no_travel_miles"] > 0:
        why = ("Every route crosses No Travel conditions; this one has the fewest No Travel miles "
               f"({b['no_travel_miles']} mi). Consider delaying departure.")
        return best, why
    if len(routes) == 1:
        return best, "Only one route was available."
    others = [i for i in range(len(routes)) if i != best]
    # find the first criterion that separates best from the runner-up
    runner = min(others, key=lambda i: keys[i])
    names = ["No Travel miles", "Severe miles", "High miles", "average risk", "travel time"]
    for idx, name in enumerate(names):
        if keys[best][idx] != keys[runner][idx]:
            r = routes[runner]["summary"]
            if idx == 1:
                return best, f"Fewest Severe miles ({b['severe_miles']} vs {r['severe_miles']} on the next best route)."
            if idx == 2:
                return best, f"Same Severe miles, but fewer High miles ({b['high_miles']} vs {r['high_miles']})."
            if idx == 3:
                return best, f"Same Severe/High miles, but lower average risk ({b['avg_risk']} vs {r['avg_risk']})."
            if idx == 4:
                return best, "Weather risk is equivalent across routes, so the shortest travel time wins."
    return best, "Routes are equivalent on all criteria; picked the fastest."
