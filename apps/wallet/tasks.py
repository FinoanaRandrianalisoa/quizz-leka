from celery import shared_task
from django.conf import settings

from apps.wallet.models import Portefeuille, LedgerEntry
from apps.wallet.services import crediter


@shared_task(queue="payments", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def traiter_depot_async(payload: dict):
    """Traitement asynchrone idempotent d'un dépôt confirmé par webhook."""
    reference = str(payload.get("transaction_id") or payload.get("id") or "")
    msisdn = payload.get("msisdn", "")
    montant = payload.get("amount", 0)
    type_ = payload.get("type", "")

    if LedgerEntry.objects.filter(idempotency_key=f"webhook:{reference}").exists():
        return {"status": "duplicate"}

    pf = Portefeuille.objects.filter(utilisateur__username__isnull=False).first()
    if not pf:
        return {"status": "no_portefeuille"}

    from decimal import Decimal

    crediter(
        pf,
        Decimal(str(montant)),
        LedgerEntry.Type.DEPOT,
        reference=f"depot-webhook-{reference}",
        metadata={"provider": payload.get("provider"), "msisdn": msisdn[-4:]},
        champ="solde_recharge",
        idempotency_key=f"webhook:{reference}",
    )
    return {"status": "ok"}
