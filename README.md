# Weather-Aware Truck Routing

React + Django app that proposes up to three driving routes, forecasts the weather the truck will
actually meet (at its *estimated arrival time* at each checkpoint), scores each route with the
supplied risk/load rules, and recommends the safest sensible one. A heatmap with a 0-48 h slider
shows the weather along the trip corridor.

## Run locally

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver            # http://localhost:8000

# frontend (second terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api to :8000)

# tests (risk engine, no Django needed)
cd backend && python -m unittest routing.tests -v
```

No API keys are required.

## Deploy (single service)

`render.yaml` builds the React app and serves it from Django (WhiteNoise), so one web service hosts
everything: `./build.sh`, then `gunicorn config.wsgi`. Set `DJANGO_ALLOWED_HOSTS` to your domain.

## Architecture

| Concern | Provider | Where |
|---|---|---|
| Geocoding | Nominatim (OSM) | `routing/clients.py::geocode` |
| Routes | OSRM public API, `alternatives=3` | `clients.get_routes` |
| Weather | Open-Meteo hourly (wind mph, rain in/hr, snowfall in/hr) | `clients.fetch_hourly` |
| Risk + ranking | pure Python, no I/O | `routing/risk.py` |
| Orchestration | checkpoints, ETAs, summaries | `routing/planner.py` |

Endpoints: `GET /api/geocode?q=`, `POST /api/plan`, `POST /api/heatmap`.

### Flow of `/api/plan`
1. Get up to 3 distinct routes. If OSRM returns fewer than 3 alternatives, extra candidates are
   created by routing through via-points offset either side of the midpoint, and kept only if they
   differ from existing routes (<85% overlap).
2. Place checkpoints every 10/25/50 miles (plus the destination). The ETA at each comes from the
   route's per-segment durations, so it reflects where the truck is on the road, not a flat average.
3. Fetch hourly forecasts for all checkpoints of all routes in batched calls (cached 15 min) and
   read the forecast hour nearest each ETA.
4. Classify each checkpoint (worst of wind/rain/snow, then load rules).
5. Each checkpoint "owns" the miles from the midpoint before it to the midpoint after it, giving
   miles per risk level, mile-weighted average risk, and a max level per route.
6. Rank routes and explain why the winner won.

### Risk rules and boundary decisions
The spec's ranges share edge values (e.g. rain 0.10-0.25 and 0.25-0.50), so every band has an
**inclusive lower bound**: wind 35.0 is High, rain 0.25 is High, snow 2.0 is Severe. No Travel is
wind >= 55, rain > 1.00, snow > 3.0 (matching the spec's symbols). Load rules only ever raise a level:
- wind >= 55 -> No Travel (any load)
- wind 45-54 and load > 30,000 lb -> No Travel
- wind 35-44 and load > 40,000 lb -> Severe

### Recommendation
Lexicographic: No Travel miles, Severe miles, High miles, average risk, travel time. Two choices to
flag:
- No Travel miles are compared first because they are strictly worse than Severe.
- Miles are compared to the nearest 1 mile and average risk to 0.05. At 10-50 mile sampling,
  finer differences are noise, and without this a 6-hour detour could "win" over 0.3 miles of Severe.
  Both constants are at the top of `risk.py`.
If every route has No Travel miles the app says so and suggests delaying.

### Heatmap
`/api/plan` returns corridor sample points (along every route every ~30 mi, plus a point 20 mi to
each side). `/api/heatmap` returns the risk level for each point for each of the next 49 hours in one
response,and needs no network. The overlay is one translucent circle per sample point, coloured by that 
point's risk level (so colour always matches the route cards), drawn on its own blurred canvas pane; 
moving the slider only restyles the existing circles. Hour 0 is the current hour; load weight is applied
to the levels.

## Known limitations
- OSRM's public server uses a **car** profile: no truck restrictions (height, weight, hazmat).
  Swapping in a truck-aware provider (e.g. OpenRouteService `driving-hgv`) only touches `get_routes`.
- Open-Meteo gives 10 m sustained wind; gusts are not used. Rain uses the `rain` field and snow uses
  `snowfall` (inches of snow per hour).
- Forecasts cover ~14 days; departures further out are rejected. Arrivals beyond the loaded forecast
  use the nearest hour and the response flags `forecast_clamped`.
- Public OSRM/Nominatim are rate-limited demo services; use your own instances for production.
- Cached with in-process memory (fine for a demo; use Redis for multi-worker production).
