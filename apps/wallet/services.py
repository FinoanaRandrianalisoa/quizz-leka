"""Services financiers du portefeuille DEMO.

Règles centralisées (backend uniquement — jamais de montant calculé côté React) :
- réservation : disponible → bloqué (atomique, idempotente) ;
- engagement : seule la mise effective `MIN(mise_A, mise_B)` est engagée ;
- règlement : commission de 20 % de la mise effective de chaque participant,
  crédit du gain net au gagnant, alimentation du capital plateforme ;
- toute opération critique est atomique (`transaction.atomic`), verrouillée
  (`select_for_update`) et idempotente (clé unique sur le ledger).
"""

from decimal import Decimal, ROUND_DOWN

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.wallet.models import Portefeuille, LedgerEntry, PlatformeWallet, PlatformeTransaction, PortefeuilleEvent
from common.graphql.errors import (
    InsufficientFundsError,
    InvalidAmountError,
    InvalidPinError,
    PinMismatchError,
    PinNotSetError,
    RechargeLimitExceededError,
    WalletLockedError,
    WalletUnlockRequiredError,
)


def _verifier_montant(montant: Decimal):
    if montant is None or montant <= 0:
        raise InvalidAmountError()
    return montant.quantize(Decimal("0.01"))


def _verifier_montant_non_negatif(montant: Decimal) -> Decimal:
    if montant is None or montant < 0:
        raise InvalidAmountError()
    return montant.quantize(Decimal("0.01"))


def _entree_existe(idempotency_key: str) -> bool:
    if not idempotency_key:
        return False
    return LedgerEntry.objects.filter(idempotency_key=idempotency_key).exists()


def _info_request(request=None) -> dict:
    if request is None:
        return {}
    ip = getattr(getattr(request, "META", {}), "get", lambda k, d=None: d)("REMOTE_ADDR")
    user_agent = getattr(getattr(request, "META", {}), "get", lambda k, d=None: d)("HTTP_USER_AGENT", "")
    return {"ip": ip, "user_agent": user_agent[:512]}


# ============================================================================
# Opérations de base sur les soldes
# ============================================================================


@transaction.atomic
def crediter(portefeuille, montant, type_, reference="", metadata=None, champ="solde_recharge", idempotency_key=""):
    """Crédite un solde via le ledger, avec verrouillage pessimiste."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    avant = getattr(pf, champ)
    setattr(pf, champ, avant + montant)
    pf.save(update_fields=[champ, "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=type_,
        montant=montant,
        solde_avant=pf.solde_total - montant if champ == "solde_recharge" or champ == "solde_gains" else None,
        solde_apres=pf.solde_total,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    return pf


@transaction.atomic
def debiter(portefeuille, montant, type_, reference="", metadata=None, champ="solde_recharge", idempotency_key=""):
    """Débite un solde via le ledger, avec verrouillage pessimiste."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    nouveau = getattr(pf, champ) - montant
    if nouveau < 0:
        raise InsufficientFundsError()
    setattr(pf, champ, nouveau)
    pf.save(update_fields=[champ, "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=type_,
        montant=-montant,
        solde_avant=pf.solde_total + montant,
        solde_apres=pf.solde_total,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    return pf


# ============================================================================
# Crédit initial & recharge DEMO
# ============================================================================


@transaction.atomic
def crediter_demo_initial(portefeuille) -> Portefeuille:
    """Dotation initiale +1 000 000 Ar DEMO, idempotente par utilisateur."""
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    cle = f"demo-initial:{pf.utilisateur_id}"
    if LedgerEntry.objects.filter(idempotency_key=cle).exists():
        return pf
    montant = Decimal(str(settings.DEMO_INITIAL_BALANCE)).quantize(Decimal("0.01"))
    pf.solde_recharge += montant
    pf.save(update_fields=["solde_recharge", "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=LedgerEntry.Type.DEMO_INITIAL_CREDIT,
        montant=montant,
        solde_avant=pf.solde_total - montant,
        solde_apres=pf.solde_total,
        reference=f"credit-initial-demo-{pf.utilisateur_id}",
        statut=LedgerEntry.Statut.SUCCES,
        metadata={"demo": True},
        idempotency_key=cle,
    )
    return pf


@transaction.atomic
def recharger_demo(portefeuille, idempotency_key: str = "", request=None) -> Portefeuille:
    """Recharge DEMO configurable, limitée à `DEMO_RECHARGE_LIMIT` par jour.

    Ne fait JAMAIS appel à MVola / Orange Money / Airtel Money.
    """
    if not idempotency_key:
        raise InvalidAmountError()
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    if _entree_existe(idempotency_key):
        return pf

    aujourd_hui = timezone.localdate()
    limite = int(settings.DEMO_RECHARGE_LIMIT or 1)
    deja_fait = LedgerEntry.objects.filter(
        portefeuille=pf,
        type=LedgerEntry.Type.DEMO_RECHARGE,
        cree_le__date=aujourd_hui,
    ).count()
    if deja_fait >= limite:
        raise RechargeLimitExceededError()

    montant = Decimal(str(settings.DEMO_RECHARGE_AMOUNT)).quantize(Decimal("0.01"))
    pf.solde_recharge += montant
    pf.derniere_recharge_le = aujourd_hui
    pf.save(update_fields=["solde_recharge", "derniere_recharge_le", "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=LedgerEntry.Type.DEMO_RECHARGE,
        montant=montant,
        solde_avant=pf.solde_total - montant,
        solde_apres=pf.solde_total,
        reference=f"recharge-demo-{pf.utilisateur_id}",
        statut=LedgerEntry.Statut.SUCCES,
        metadata={"demo": True},
        idempotency_key=idempotency_key,
        **_info_request(request),
    )
    return pf


# ============================================================================
# Réservation / engagement / libération / consommation d'une mise
# ============================================================================


@transaction.atomic
def bloquer_mise(portefeuille, montant, reference="", metadata=None, idempotency_key=""):
    """Réserve une mise : disponible → bloqué (login ledger 'mise réservée')."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    if pf.solde_recharge < montant:
        raise InsufficientFundsError()
    pf.solde_recharge -= montant
    pf.solde_bloque += montant
    pf.save(update_fields=["solde_recharge", "solde_bloque", "modifie_le"])
    bloc_avant = pf.solde_bloque - montant
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=LedgerEntry.Type.MISE_BLOQUEE,
        montant=-montant,
        solde_avant=pf.solde_total + montant,
        solde_apres=pf.solde_total,
        bloque_avant=bloc_avant,
        bloque_apres=pf.solde_bloque,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    return pf


@transaction.atomic
def engager_mise(portefeuille, montant, reference="", metadata=None):
    """Marque l'engagement définitif d'une mise (aucun mouvement de solde)."""
    montant = _verifier_montant(montant)
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=LedgerEntry.Type.MISE_ENGAGEE,
        montant=-montant,
        solde_avant=pf.solde_total,
        solde_apres=pf.solde_total,
        bloque_avant=pf.solde_bloque,
        bloque_apres=pf.solde_bloque,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
    )
    return pf


@transaction.atomic
def liberer_mise(portefeuille, montant, reference="", metadata=None, type_=LedgerEntry.Type.MISE_LIBEREE, idempotency_key=""):
    """Libère une mise : bloqué → disponible (remboursement 100 %, sans commission)."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    releve = min(montant, pf.solde_bloque)
    pf.solde_bloque -= releve
    pf.solde_recharge += releve
    pf.save(update_fields=["solde_bloque", "solde_recharge", "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=type_,
        montant=releve,
        solde_avant=pf.solde_total - releve,
        solde_apres=pf.solde_total,
        bloque_avant=pf.solde_bloque + releve,
        bloque_apres=pf.solde_bloque,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    return pf


@transaction.atomic
def consommer_mise(portefeuille, montant, type_=LedgerEntry.Type.PERTE, reference="", metadata=None, idempotency_key=""):
    """Consomme définitivement une mise bloquée (défaite)."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    releve = min(montant, pf.solde_bloque)
    pf.solde_bloque -= releve
    pf.save(update_fields=["solde_bloque", "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=pf,
        type=type_,
        montant=-montant,
        solde_avant=pf.solde_total + montant,
        solde_apres=pf.solde_total,
        bloque_avant=pf.solde_bloque + releve,
        bloque_apres=pf.solde_bloque,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata=metadata or {},
        idempotency_key=idempotency_key,
    )
    return pf


@transaction.atomic
def payer_gain(portefeuille, *, mise, montant_brut, commission=Decimal("0"), reference="", metadata=None, idempotency_key=""):
    """Crédite un gain net au gagnant et consomme sa mise engagée.

    `montant_brut` : le pot redistribuable avant commission.
    `commission`   : part plateforme (déjà déduite du gain net).
    """
    mise = _verifier_montant(mise)
    montant_brut = _verifier_montant(montant_brut)
    commission = _verifier_montant_non_negatif(commission)
    if commission >= montant_brut:
        commission = montant_brut
    net = (montant_brut - commission).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    if _entree_existe(idempotency_key):
        return portefeuille

    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    pf.solde_gains += net
    releve = min(mise, pf.solde_bloque)
    pf.solde_bloque -= releve
    pf.save(update_fields=["solde_gains", "solde_bloque", "modifie_le"])

    LedgerEntry.objects.create(
        portefeuille=pf,
        type=LedgerEntry.Type.GAIN,
        montant=net,
        solde_avant=pf.solde_total - net,
        solde_apres=pf.solde_total,
        bloque_avant=pf.solde_bloque + releve,
        bloque_apres=pf.solde_bloque,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata={**(metadata or {}), "gain_brut": str(montant_brut)},
        idempotency_key=idempotency_key,
    )
    if commission > 0:
        LedgerEntry.objects.create(
            portefeuille=pf,
            type=LedgerEntry.Type.COMMISSION,
            montant=-commission,
            solde_avant=pf.solde_total,
            solde_apres=pf.solde_total,
            reference=reference,
            statut=LedgerEntry.Statut.SUCCES,
            metadata={**(metadata or {}), "commission": str(commission)},
            idempotency_key=f"{idempotency_key}:commission" if idempotency_key else "",
        )
    return pf


# ============================================================================
# Capital plateforme
# ============================================================================


@transaction.atomic
def crediter_plateforme(montant, *, type_=PlatformeTransaction.Type.COMMISSION, reference="", game_id="", bet_id="", metadata=None):
    """Alimente le capital plateforme (commissions réellement encaissées)."""
    montant = _verifier_montant(montant)
    pw = PlatformeWallet.objects.select_for_update().get_or_create(pk=1)[0]
    avant = pw.capital
    pw.capital += montant
    pw.save(update_fields=["capital", "modifie_le"])
    PlatformeTransaction.objects.create(
        platforme=pw,
        type=type_,
        montant=montant,
        capital_avant=avant,
        capital_apres=pw.capital,
        reference=reference,
        game_id=game_id,
        bet_id=bet_id,
        metadata=metadata or {},
    )
    return pw


@transaction.atomic
def ajuster_plateforme(montant, reference="", metadata=None):
    """Transaction compensatoire : corrige le capital sans jamais modifier l'historique."""
    pw = PlatformeWallet.objects.select_for_update().get_or_create(pk=1)[0]
    avant = pw.capital
    pw.capital += montant
    pw.save(update_fields=["capital", "modifie_le"])
    PlatformeTransaction.objects.create(
        platforme=pw,
        type=PlatformeTransaction.Type.AJUSTEMENT,
        montant=montant,
        capital_avant=avant,
        capital_apres=pw.capital,
        reference=reference,
        metadata=metadata or {},
    )
    return pw


# ============================================================================
# Règlement des duels (GameSettlementService)
# ============================================================================


class GameSettlementService:
    """Service central de règlement financier.

    Responsabilités : déterminer la mise effective, calculer les commissions,
    créditer le gagnant, alimenter le capital plateforme, empêcher les doubles
    règlements. Ne dépend d'aucun fournisseur de paiement.
    """

    @staticmethod
    def commission_pour(mise_effective: Decimal) -> Decimal:
        taux = Decimal(str(getattr(settings, "COMMISSION_DEMO_RATE", 0.20)))
        return (mise_effective * taux).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    @staticmethod
    def pot_net(mise_effective: Decimal) -> Decimal:
        commission_totale = GameSettlementService.commission_pour(mise_effective) * 2
        brute = (mise_effective * 2).quantize(Decimal("0.01"))
        return (brute - commission_totale).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    @staticmethod
    def regler_duel(*, portefeuille_gagnant, portefeuille_perdant, mise_effective, reference, metadata=None):
        """Règle un duel : le perdant perd sa mise effective, le gagnant reçoit
        le pot net, la plateforme encaisse 2 × 20 % de la mise effective.

        Appeler uniquement dans un `transaction.atomic()` déjà ouvert avec la
        ligne du match verrouillée (`select_for_update`) pour garantir un seul
        règlement.
        """
        mise_effective = _verifier_montant(mise_effective)
        gagnant = Portefeuille.objects.select_for_update().get(pk=portefeuille_gagnant.pk)
        perdant = Portefeuille.objects.select_for_update().get(pk=portefeuille_perdant.pk)

        cle_perdant = f"settle:{reference}:perdant"
        cle_gagnant = f"settle:{reference}:gagnant"
        if _entree_existe(cle_perdant) and _entree_existe(cle_gagnant):
            return {"statut": "deja_regle"}

        commission_totale = GameSettlementService.commission_pour(mise_effective) * 2
        pot_net = GameSettlementService.pot_net(mise_effective)

        consommer_mise(
            perdant,
            mise_effective,
            type_=LedgerEntry.Type.PERTE,
            reference=reference,
            metadata={**(metadata or {}), "role": "perdant"},
            idempotency_key=cle_perdant,
        )
        payer_gain(
            gagnant,
            mise=mise_effective,
            montant_brut=mise_effective * 2,
            commission=commission_totale,
            reference=reference,
            metadata={**(metadata or {}), "role": "gagnant"},
            idempotency_key=cle_gagnant,
        )
        crediter_plateforme(
            commission_totale,
            reference=reference,
            game_id=str(metadata.get("match") or "") if metadata else "",
            metadata={**(metadata or {}), "mise_effective": str(mise_effective)},
        )
        return {
            "statut": "regle",
            "mise_effective": mise_effective,
            "commission_totale": commission_totale,
            "pot_net": pot_net,
        }


# ============================================================================
# Sécurité PIN portefeuille (4 chiffres, distinct du mot de passe)
# ============================================================================


def _valider_pin_format(pin: str):
    if not pin or not pin.isdigit() or len(pin) != int(settings.WALLET_PIN_LENGTH):
        raise InvalidPinError()
    return pin


@transaction.atomic
def definir_pin(portefeuille, pin: str, pin_confirmation: str, request=None) -> Portefeuille:
    """Définit le PIN portefeuille. Distinct du mot de passe de connexion."""
    _valider_pin_format(pin)
    if pin != pin_confirmation:
        raise PinMismatchError()
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    if pf.pin_defini:
        raise PinMismatchError("Un PIN est déjà défini. Utilisez la modification de PIN.")
    pf.pin_hash = make_password(pin)
    pf.is_locked = True
    pf.pin_failed_attempts = 0
    pf.save(update_fields=["pin_hash", "is_locked", "pin_failed_attempts", "modifie_le"])
    PortefeuilleEvent.objects.create(
        portefeuille=pf,
        type=PortefeuilleEvent.Type.PIN_SET,
        **_info_request(request),
    )
    return pf


@transaction.atomic
def changer_pin(portefeuille, pin_actuel: str, nouveau_pin: str, confirmation: str, request=None) -> Portefeuille:
    """Modifie le PIN après vérification de l'ancien (transaction compensatoire)."""
    _valider_pin_format(nouveau_pin)
    if nouveau_pin != confirmation:
        raise PinMismatchError()
    pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
    if not pf.pin_defini or not check_password(pin_actuel, pf.pin_hash):
        raise InvalidPinError()
    pf.pin_hash = make_password(nouveau_pin)
    pf.pin_failed_attempts = 0
    pf.save(update_fields=["pin_hash", "pin_failed_attempts", "modifie_le"])
    PortefeuilleEvent.objects.create(
        portefeuille=pf,
        type=PortefeuilleEvent.Type.PIN_CHANGED,
        **_info_request(request),
    )
    return pf


def verifier_pin(portefeuille, pin: str) -> bool:
    if not portefeuille.pin_defini:
        raise PinNotSetError()
    return check_password(pin, portefeuille.pin_hash)


def deverrouiller_portefeuille(portefeuille, pin: str, request=None) -> Portefeuille:
    """Déverrouillage temporaire du portefeuille avec le PIN + anti brute-force.

    Toute la logique s'exécute dans une transaction afin de pouvoir utiliser
    `select_for_update()` (interdit hors transaction sur Postgres). Les
    tentatives ratées sont persistées dans un point de sauvegarde dédié qui est
    validé AVANT que l'erreur métier ne soit levée à l'extérieur de la
    transaction : le compteur d'échecs n'est donc jamais annulé.
    """
    erreur = None
    verrouille = False
    with transaction.atomic():
        pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
        maintenant = timezone.now()

        if pf.is_locked and pf.locked_until and maintenant < pf.locked_until:
            raise WalletLockedError()

        if not pf.pin_defini:
            raise PinNotSetError()

        # Un verrouillage expiré est automatiquement levé (nouvelle tentative autorisée).
        if pf.is_locked and pf.locked_until and maintenant >= pf.locked_until:
            pf.is_locked = False
            pf.pin_failed_attempts = 0
            pf.locked_until = None
            pf.save(update_fields=["is_locked", "pin_failed_attempts", "locked_until", "modifie_le"])

        valide = check_password(pin, pf.pin_hash)
        if not valide:
            # Enregistre l'échec, puis lève l'erreur UNIQUEMENT après validation
            # du savepoint (sinon le compteur serait annulé par le rollback).
            with transaction.atomic():
                pf.pin_failed_attempts += 1
                PortefeuilleEvent.objects.create(
                    portefeuille=pf,
                    type=PortefeuilleEvent.Type.PIN_FAILED,
                    metadata={"attempts": pf.pin_failed_attempts},
                    **_info_request(request),
                )
                verrouille = pf.pin_failed_attempts >= int(settings.WALLET_PIN_MAX_ATTEMPTS)
                if verrouille:
                    pf.is_locked = True
                    pf.locked_until = maintenant + timezone.timedelta(seconds=int(settings.WALLET_PIN_LOCK_DURATION))
                    pf.save(update_fields=["pin_failed_attempts", "is_locked", "locked_until", "modifie_le"])
                    PortefeuilleEvent.objects.create(
                        portefeuille=pf,
                        type=PortefeuilleEvent.Type.WALLET_LOCKED,
                        metadata={"until": pf.locked_until.isoformat()},
                        **_info_request(request),
                    )
                else:
                    pf.save(update_fields=["pin_failed_attempts", "modifie_le"])
            erreur = WalletLockedError() if verrouille else InvalidPinError()

        else:  # PIN valide → déverrouillage temporaire
            pf.is_locked = False
            pf.pin_failed_attempts = 0
            pf.locked_until = None
            pf.unlocked_until = maintenant + timezone.timedelta(seconds=int(settings.WALLET_PIN_UNLOCK_DURATION))
            pf.save(update_fields=["is_locked", "pin_failed_attempts", "locked_until", "unlocked_until", "modifie_le"])
            PortefeuilleEvent.objects.create(
                portefeuille=pf,
                type=PortefeuilleEvent.Type.WALLET_UNLOCKED,
                metadata={"until": pf.unlocked_until.isoformat()},
                **_info_request(request),
            )

    if erreur:
        raise erreur
    return pf


def est_deverrouille(portefeuille) -> bool:
    """True si le portefeuille est déverrouillé (verrouillage auto à expiration)."""
    if not portefeuille.pin_defini:
        return False
    maintenant = timezone.now()
    if portefeuille.is_locked:
        if portefeuille.locked_until and maintenant >= portefeuille.locked_until:
            return True
        return False
    if portefeuille.unlocked_until and maintenant >= portefeuille.unlocked_until:
        # Verrouillage automatique après expiration
        try:
            with transaction.atomic():
                pf = Portefeuille.objects.select_for_update().get(pk=portefeuille.pk)
                pf.is_locked = True
                pf.save(update_fields=["is_locked", "modifie_le"])
                PortefeuilleEvent.objects.create(
                    portefeuille=pf,
                    type=PortefeuilleEvent.Type.WALLET_LOCKED,
                    metadata={"auto": True},
                )
            portefeuille.is_locked = True
        except Exception:  # pragma: no cover
            pass
        return False
    return True


def exiger_deverrouille(portefeuille) -> None:
    """Lève une erreur si le portefeuille doit être (re)déverrouillé."""
    if not portefeuille.pin_defini:
        raise PinNotSetError()
    if not est_deverrouille(portefeuille):
        raise WalletUnlockRequiredError()


# ============================================================================
# Transfert DEMO (optionnel — activable)
# ============================================================================


@transaction.atomic
def transferer_demo(portefeuille_emetteur, portefeuille_recepteur, montant, reference="", idempotency_key="", request=None):
    """Transfert DEMO entre utilisateurs : débit + crédit atomiques."""
    montant = _verifier_montant(montant)
    if _entree_existe(idempotency_key):
        return portefeuille_emetteur
    emetteur = Portefeuille.objects.select_for_update().get(pk=portefeuille_emetteur.pk)
    if emetteur.solde_recharge < montant:
        raise InsufficientFundsError()
    recip = Portefeuille.objects.select_for_update().get(pk=portefeuille_recepteur.pk)
    emetteur.solde_recharge -= montant
    recip.solde_recharge += montant
    emetteur.save(update_fields=["solde_recharge", "modifie_le"])
    recip.save(update_fields=["solde_recharge", "modifie_le"])
    LedgerEntry.objects.create(
        portefeuille=emetteur,
        type=LedgerEntry.Type.TRANSFERT,
        montant=-montant,
        solde_avant=emetteur.solde_total + montant,
        solde_apres=emetteur.solde_total,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata={"sens": "emetteur", "destinataire": recip.utilisateur_id},
        idempotency_key=idempotency_key,
        **_info_request(request),
    )
    LedgerEntry.objects.create(
        portefeuille=recip,
        type=LedgerEntry.Type.TRANSFERT,
        montant=montant,
        solde_avant=recip.solde_total - montant,
        solde_apres=recip.solde_total,
        reference=reference,
        statut=LedgerEntry.Statut.SUCCES,
        metadata={"sens": "recepteur", "emetteur": emetteur.utilisateur_id},
        idempotency_key=f"{idempotency_key}:recip" if idempotency_key else "",
        **_info_request(request),
    )
    return emetteur


# ============================================================================
# Dashboard financier ADMIN
# ============================================================================


def _somme_abs(entries):
    return sum((abs(e.montant) for e in entries), Decimal("0.00"))


def _fin_du_jour(date_jour):
    from datetime import timedelta
    return timezone.make_aware(timezone.datetime.combine(date_jour, timezone.datetime.min.time())) + timedelta(days=1) - timedelta(microseconds=1)


def statistiques_financieres(depuis=None, jusqu_a=None) -> dict:
    """KPI financiers globaux — réservés ADMIN (contrôle d'accès côté backend)."""
    from apps.matches.models import Match, Participation
    from apps.betting.models import Pari
    from django.contrib.auth import get_user_model

    Utilisateur = get_user_model()
    entries = LedgerEntry.objects.select_related("portefeuille__utilisateur")
    if depuis:
        entries = entries.filter(cree_le__date__gte=depuis)
    if jusqu_a:
        entries = entries.filter(cree_le__lte=_fin_du_jour(jusqu_a))

    total_distribue = Decimal("0.00")
    total_mise = Decimal("0.00")
    nb_mises = 0
    total_gagne = Decimal("0.00")
    total_perdu = Decimal("0.00")
    total_commissions = Decimal("0.00")
    commissions_par_portefeuille = {}

    for e in entries.iterator():
        montant = e.montant
        if e.type in (LedgerEntry.Type.DEMO_INITIAL_CREDIT, LedgerEntry.Type.DEMO_RECHARGE):
            total_distribue += montant
        elif e.type == LedgerEntry.Type.MISE_ENGAGEE:
            total_mise += abs(montant)
            nb_mises += 1
        elif e.type == LedgerEntry.Type.GAIN and montant > 0:
            total_gagne += montant
        elif e.type == LedgerEntry.Type.PERTE:
            total_perdu += abs(montant)
        elif e.type == LedgerEntry.Type.COMMISSION:
            total_commissions += abs(montant)
            pf_key = e.portefeuille_id
            commissions_par_portefeuille[pf_key] = commissions_par_portefeuille.get(pf_key, Decimal("0.00")) + abs(montant)

    solde_detenu = sum((w.solde_total for w in Portefeuille.objects.all()), Decimal("0.00"))
    capital = PlatformeWallet.singleton().capital

    joueurs_count = Utilisateur.objects.filter(role="JOUEUR").count()
    if joueurs_count == 0:
        joueurs_count = Utilisateur.objects.count()

    nombre_matchs = Match.objects.count()
    mise_moyenne = (total_mise / nb_mises).quantize(Decimal("0.01")) if nb_mises else Decimal("0.00")

    meilleur_joueur = None
    best_participation = (
        Participation.objects.filter(vainqueur=True, match__statut=Match.Statut.TERMINE)
        .values("utilisateur__pseudo")
        .annotate(victoires=Count("id"))
        .order_by("-victoires")
        .first()
    )
    if best_participation:
        meilleur_joueur = (
            best_participation["utilisateur__pseudo"],
            str(best_participation["victoires"]),
            "victoires",
        )

    meilleur_generateur_commissions = None
    if commissions_par_portefeuille:
        top_pf_id = max(commissions_par_portefeuille, key=commissions_par_portefeuille.get)
        try:
            top_pf = Portefeuille.objects.select_related("utilisateur").get(pk=top_pf_id)
            meilleur_generateur_commissions = (
                top_pf.utilisateur.pseudo,
                str(commissions_par_portefeuille[top_pf_id].quantize(Decimal("0.01"))),
                "commissions Ar",
            )
        except Portefeuille.DoesNotExist:
            pass

    return {
        "nombre_joueurs": joueurs_count,
        "solde_total_distribue": total_distribue,
        "solde_detenu_par_joueurs": solde_detenu,
        "total_mise": total_mise,
        "total_gagne": total_gagne,
        "total_perdu": total_perdu,
        "total_commissions": total_commissions,
        "capital_plateforme": capital,
        "nombre_matchs": nombre_matchs,
        "nombre_paris": Pari.objects.count(),
        "mise_moyenne": mise_moyenne,
        "meilleur_joueur": meilleur_joueur,
        "meilleur_generateur_commissions": meilleur_generateur_commissions,
    }