import hashlib
import time

from django.core.cache import cache
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

MAX_DOWNLOAD_BYTES = 256 * 1024
DEFAULT_DOWNLOAD_BYTES = 128 * 1024
MAX_UPLOAD_BYTES = 128 * 1024
# Le moniteur de connexion du front émet ~16 requêtes/minute/tab.
# Sur un NAT partagé (4G, entreprise…) de nombreux utilisateurs partagent la
# même IP : on doit laisser une marge confortable pour ne pas blocker les pings.
RATE_LIMIT_PER_MINUTE = 240
RATE_WINDOW_SECONDS = 60


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_key(request):
    """Clé par (IP + empreinte User-Agent).

    Tous les clients derrière un même NAT partagent l'IP : on désamorce avec
    l'agent pour répartir les quotas plutôt que de bloquer tout le monde d'un
    coup dès qu'un des utilisateurs dépasse le budget.
    """
    ip = _client_ip(request)
    try:
        agent = request.META.get("HTTP_USER_AGENT", "").encode("utf-8", "ignore")
        digest = hashlib.sha256(agent).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        digest = "unknown"
    return f"connection-test:{ip}:{digest}"


def _rate_limited(request):
    key = _rate_limit_key(request)
    try:
        count = cache.get(key, 0)
        if count >= RATE_LIMIT_PER_MINUTE:
            return True
        cache.set(key, count + 1, timeout=RATE_WINDOW_SECONDS)
    except Exception:  # noqa: BLE001
        return False
    return False


def _too_many():
    return JsonResponse(
        {"ok": False, "error": "too_many_requests"},
        status=429,
    )


@csrf_exempt
@require_GET
def ping(request):
    if _rate_limited(request):
        return _too_many()
    return JsonResponse({"ok": True, "t": time.time()})


@csrf_exempt
@require_GET
def download(request):
    if _rate_limited(request):
        return _too_many()
    try:
        size = int(request.GET.get("size", DEFAULT_DOWNLOAD_BYTES))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("invalid size")
    size = max(1, min(size, MAX_DOWNLOAD_BYTES))
    payload = b"Q" * size
    response = HttpResponse(payload, content_type="application/octet-stream")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response["Content-Length"] = str(size)
    return response


@csrf_exempt
@require_POST
def upload(request):
    if _rate_limited(request):
        return _too_many()
    body = request.body or b""
    if len(body) > MAX_UPLOAD_BYTES:
        return JsonResponse(
            {"ok": False, "error": "payload_too_large"},
            status=413,
        )
    return JsonResponse({"ok": True, "bytes": len(body)})
