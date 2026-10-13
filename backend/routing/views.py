import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import clients, planner


def _json_body(request) -> dict:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise planner.ValidationError(f"Invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise planner.ValidationError("Body must be a JSON object")
    return body


def _guard(fn):
    """Map domain errors to clean JSON responses."""
    def wrapper(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except planner.ValidationError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except clients.UpstreamError as exc:
            return JsonResponse({"error": str(exc)}, status=502)
    wrapper.__name__ = fn.__name__
    return wrapper


@require_GET
def health(request):
    return JsonResponse({"ok": True})


@require_GET
@_guard
def geocode(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 3:
        return JsonResponse({"results": []})
    return JsonResponse({"results": clients.geocode(q)})


@require_POST
@_guard
def plan(request):
    return JsonResponse(planner.plan(_json_body(request)))


@require_POST
@_guard
def heatmap(request):
    body = _json_body(request)
    try:
        points = list(body["points"])
        load_lb = float(body.get("load_lb", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise planner.ValidationError(f"Invalid or missing field: {exc}") from exc
    return JsonResponse(planner.heatmap(points, load_lb))
