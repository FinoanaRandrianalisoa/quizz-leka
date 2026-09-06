import json
import time
import hashlib
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.wallet.models import LedgerEntry
from apps.wallet.services import crediter
from apps.wallet.tasks import traiter_depot_async


def _verifier_signature(request) -> bool:
    signature = request.headers.get("X-Webhook-Signature", "")
    secret = settings.MOBILE_MONEY_WEBHOOK_SECRET
    if not secret:
        return False
    body = request.body
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


@csrf_exempt
@require_POST
def mobile_money_webhook(request):
    """Endpoint REST des webhooks Mobile Money.

    Répond 200 dès que le webhook est accepté pour traitement asynchrone.
    Les 4xx couvrent les payloads/signatures invalides, les 5xx les erreurs serveur.
    """
    if not _verifier_signature(request):
        return JsonResponse({"error": "signature invalide"}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "payload malformé"}, status=400)

    traiter_depot_async.delay(payload)
    return JsonResponse({"accepted": True}, status=200)
