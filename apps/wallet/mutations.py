from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.wallet import services
from apps.wallet.models import Portefeuille, LedgerEntry, PortefeuilleEvent
from apps.wallet.types import PortefeuilleType
from common.graphql.errors import (
    InvalidAmountError,
    DuplicateIdempotencyKeyError,
    WithdrawalAlreadyPendingError,
    InvalidOtpError,
)
from common.graphql.permissions import get_current_user


@strawberry.type
class WalletMutation:
    @strawberry.mutation
    def effectuer_depot(
        info: Info,
        montant: Decimal,
        method: str,
        idempotency_key: str,
        phone_number: str,
    ) -> PortefeuilleType:
        """Déclenche un dépôt Mobile Money. Traitement async via Celery."""
        user = get_current_user(info)
        pf = Portefeuille.objects.get(utilisateur=user)
        if LedgerEntry.objects.filter(idempotency_key=idempotency_key).exists():
            raise DuplicateIdempotencyKeyError()
        pf = services.crediter(
            pf,
            montant,
            LedgerEntry.Type.DEPOT,
            reference=f"depot-{method}",
            metadata={"provider": method, "phone": phone_number[-4:]},
            champ="solde_recharge",
            idempotency_key=idempotency_key,
        )
        return pf

    @strawberry.mutation
    def demander_retrait(
        info: Info,
        montant: Decimal,
        phone_number: str,
        otp_token: str,
        idempotency_key: str,
    ) -> PortefeuilleType:
        user = get_current_user(info)
        # Vérification du token step-up (OTP déjà validé)
        import jwt
        from django.conf import settings

        try:
            payload = jwt.decode(otp_token, settings.JWT_SECRET, algorithms=["HS256"])
            assert payload.get("type") == "stepup" and payload.get("sub") == str(user.id)
        except Exception:
            raise InvalidOtpError()

        if LedgerEntry.objects.filter(idempotency_key=idempotency_key).exists():
            raise DuplicateIdempotencyKeyError()
        if Portefeuille.objects.filter(
            utilisateur=user,
            ledger_entries__type=LedgerEntry.Type.RETRAIT,
            ledger_entries__statut=LedgerEntry.Statut.PENDING,
        ).exists():
            raise WithdrawalAlreadyPendingError()

        pf = services.debiter(
            Portefeuille.objects.get(utilisateur=user),
            montant,
            LedgerEntry.Type.RETRAIT,
            reference="retrait-manuel",
            metadata={"phone": phone_number[-4:]},
            champ="solde_recharge",
            idempotency_key=idempotency_key,
        )
        return pf

    # ------------------------------------------------------------------
    # Portefeuille DEMO
    # ------------------------------------------------------------------

    @strawberry.mutation
    def definir_pin_portefeuille(
        info: Info,
        pin: str,
        pin_confirmation: str,
    ) -> PortefeuilleType:
        user = get_current_user(info)
        pf = services.definir_pin(
            Portefeuille.objects.get(utilisateur=user),
            pin,
            pin_confirmation,
            request=info.context.request,
        )
        return pf

    @strawberry.mutation
    def changer_pin_portefeuille(
        info: Info,
        pin_actuel: str,
        nouveau_pin: str,
        confirmation: str,
    ) -> PortefeuilleType:
        user = get_current_user(info)
        pf = services.changer_pin(
            Portefeuille.objects.get(utilisateur=user),
            pin_actuel,
            nouveau_pin,
            confirmation,
            request=info.context.request,
        )
        return pf

    @strawberry.mutation
    def deverrouiller_portefeuille(info: Info, pin: str) -> PortefeuilleType:
        user = get_current_user(info)
        pf = services.deverrouiller_portefeuille(
            Portefeuille.objects.get(utilisateur=user),
            pin,
            request=info.context.request,
        )
        return pf

    @strawberry.mutation
    def verrouiller_portefeuille(info: Info) -> PortefeuilleType:
        user = get_current_user(info)
        pf = Portefeuille.objects.get(utilisateur=user)
        pf.is_locked = True
        pf.unlocked_until = None
        pf.save(update_fields=["is_locked", "unlocked_until", "modifie_le"])
        PortefeuilleEvent.objects.create(
            portefeuille=pf,
            type=PortefeuilleEvent.Type.WALLET_LOCKED,
            metadata={"manuel": True},
        )
        return pf

    @strawberry.mutation
    def recharger_portefeuille(info: Info, idempotency_key: str) -> PortefeuilleType:
        """Recharge DEMO : PIN requis, max 1 fois par jour, jamais un retrait réel."""
        user = get_current_user(info)
        pf = Portefeuille.objects.get(utilisateur=user)
        services.exiger_deverrouille(pf)
        pf = services.recharger_demo(
            pf,
            idempotency_key=idempotency_key,
            request=info.context.request,
        )
        return pf