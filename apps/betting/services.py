from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.betting.models import Pari, SignalFraude
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry
from common.graphql.errors import (
    BettingClosedError,
    SelfBettingError,
    CollusionRiskError,
    MatchNotFoundError,
    NotFoundError,
    ValidationError,
)


def _lien_familial(utilisateur, joueur_pari) -> bool:
    """Parrain / filleul direct — mise interdite (RG-BET anti-collusion)."""
    if utilisateur.code_parent and utilisateur.code_parent == joueur_pari.code_parrain:
        return True
    if joueur_pari.code_parent and joueur_pari.code_parent == utilisateur.code_parrain:
        return True
    return False


def placer_pari(utilisateur, match, joueur_id: int, montant, idempotency_key: str = "") -> Pari:
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ValidationError("Montant de mise invalide.")

    if match.statut in ("termine", "annule"):
        raise BettingClosedError()
    if match.statut == "en_attente":
        raise BettingClosedError("Les paris s'ouvrent au début du match.")

    joueur_pari = None
    for candidat in (match.joueur_hote, match.joueur_invite):
        if candidat and candidat.pk == joueur_id:
            joueur_pari = candidat
            break
    if not joueur_pari:
        raise NotFoundError("Joueur introuvable dans ce match.")

    # RG-BET anti-fraude : interdictions bloquantes.
    if utilisateur.pk == match.joueur_hote_id or utilisateur.pk == match.joueur_invite_id:
        raise SelfBettingError()
    if _lien_familial(utilisateur, joueur_pari):
        raise CollusionRiskError()
    if joueur_pari == utilisateur:
        raise SelfBettingError()

    if match.premier_tiers_atteint:
        raise BettingClosedError()

    if not hasattr(utilisateur, "portefeuille"):
        raise ValidationError("Portefeuille introuvable.")
    if montant > utilisateur.portefeuille.solde_recharge:
        from common.graphql.errors import InsufficientFundsError

        raise InsufficientFundsError()

    from django.db import transaction

    with transaction.atomic():
        pari = Pari(
            utilisateur=utilisateur,
            match=match,
            joueur_pari=joueur_pari,
            montant=montant,
            cote=Decimal("2.00"),
        )
        pari.save()
        if match.mise > 0:
            wallet_services.bloquer_mise(
                utilisateur.portefeuille,
                montant,
                reference=f"pari-{pari.pk}",
                metadata={"match": match.pk, "pari": pari.pk},
                idempotency_key=idempotency_key or f"pari:{utilisateur.pk}:{match.pk}:{montant}",
            )
    
    # Diffuser le nouveau pari en temps réel aux spectateurs du match
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"match_{match.pk}",
            {
                "type": "match.event",
                "data": {
                    "event_type": "nouveau_pari",
                    "pari": {
                        "id": pari.pk,
                        "montant": str(pari.montant),
                        "cote": str(pari.cote),
                        "statut": pari.statut,
                        "utilisateur_pseudo": utilisateur.pseudo,
                        "joueur_pari_pseudo": joueur_pari.pseudo,
                        "joueur_pari_id": joueur_pari.pk,
                    },
                },
            },
        )
    
    return pari


def resoudre_paris(match) -> None:
    """Résout les paris d'un match clôturé (RG-BET-03).

    Règles financières :
      - match annulé → la mise réservée est libérée (jamais déduite) ;
      - pari gagnant → pot = montant × cote, la plateforme encaisse la commission
        sur la mise, le joueur reçoit le gain net ;
      - pari perdant → la mise réservée est consommée.
    """
    paris = match.paris.filter(statut=Pari.Statut.EN_COURS).select_related("utilisateur__portefeuille", "joueur_pari")
    for pari in paris:
        pf = pari.utilisateur.portefeuille
        if match.statut == "annule":
            wallet_services.liberer_mise(
                pf,
                pari.montant,
                type_=LedgerEntry.Type.REMBOURSEMENT,
                reference=f"remboursement-pari-{pari.pk}",
                metadata={"match": match.pk, "pari": pari.pk},
                idempotency_key=f"pari:rembourse:{pari.pk}",
            )
            pari.statut = Pari.Statut.REMBOURSE
        elif match.vainqueur_id == pari.joueur_pari_id:
            pot = (pari.montant * pari.cote).quantize(Decimal("0.01"))
            commission = wallet_services.GameSettlementService.commission_pour(pari.montant)
            wallet_services.payer_gain(
                pf,
                mise=pari.montant,
                montant_brut=pot,
                commission=commission,
                reference=f"gain-pari-{pari.pk}",
                metadata={"match": match.pk, "pari": pari.pk},
                idempotency_key=f"pari:gagne:{pari.pk}",
            )
            wallet_services.crediter_plateforme(
                commission,
                reference=f"gain-pari-{pari.pk}",
                bet_id=str(pari.pk),
                metadata={"match": match.pk, "pari": pari.pk},
            )
            pari.statut = Pari.Statut.GAGNE
        else:
            wallet_services.consommer_mise(
                pf,
                pari.montant,
                type_=LedgerEntry.Type.PERTE,
                reference=f"perte-pari-{pari.pk}",
                metadata={"match": match.pk, "pari": pari.pk},
                idempotency_key=f"pari:perdu:{pari.pk}",
            )
            pari.statut = Pari.Statut.PERDU
        pari.save(update_fields=["statut"])