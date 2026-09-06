from datetime import date

import strawberry
from strawberry.types import Info

from apps.wallet import services
from apps.wallet.models import Portefeuille, LedgerEntry, PlatformeWallet, PlatformeTransaction
from apps.wallet.types import (
    PortefeuilleType,
    LedgerEntryType,
    PlatformeWalletType,
    PlatformeTransactionType,
    FinanceAdminType,
    FinanceAdminJoueurType,
)
from common.graphql.permissions import get_current_user, require_admin


def resolve_mon_portefeuille(info: Info) -> PortefeuilleType:
    return Portefeuille.objects.get(utilisateur=get_current_user(info))


def resolve_historique(info: Info, limit: int = 20, offset: int = 0) -> list[LedgerEntryType]:
    return list(
        LedgerEntry.objects.filter(portefeuille__utilisateur=get_current_user(info))
        .order_by("-cree_le")[offset : offset + min(limit, 50)]
    )


def resolve_capital_plateforme(info: Info) -> PlatformeWalletType:
    require_admin(info)
    return PlatformeWalletType.from_model(PlatformeWallet.singleton())


def resolve_transactions_plateforme(info: Info, limit: int = 20) -> list[PlatformeTransactionType]:
    require_admin(info)
    return list(PlatformeTransaction.objects.select_related("platforme").order_by("-cree_le")[: min(limit, 50)])


def resolve_finance_admin(
    info: Info,
    depuis: date | None = None,
    jusqu_a: date | None = None,
) -> FinanceAdminType:
    require_admin(info)
    stats = services.statistiques_financieres(depuis=depuis, jusqu_a=jusqu_a)

    def joueur(slot):
        if not slot:
            return None
        return FinanceAdminJoueurType(
            id="",
            pseudo=slot[0],
            valeur=slot[1],
            detail=slot[2] if len(slot) > 2 else None,
        )

    return FinanceAdminType(
        nombre_joueurs=stats["nombre_joueurs"],
        solde_total_distribue=str(stats["solde_total_distribue"]),
        solde_detenu_par_joueurs=str(stats["solde_detenu_par_joueurs"]),
        total_mise=str(stats["total_mise"]),
        total_gagne=str(stats["total_gagne"]),
        total_perdu=str(stats["total_perdu"]),
        total_commissions=str(stats["total_commissions"]),
        capital_plateforme=str(stats["capital_plateforme"]),
        nombre_matchs=stats["nombre_matchs"],
        mise_moyenne=str(stats["mise_moyenne"]),
        meilleur_joueur=joueur(stats["meilleur_joueur"]),
        meilleur_generateur_commissions=joueur(stats["meilleur_generateur_commissions"]),
        nombre_paris=stats["nombre_paris"],
    )


@strawberry.type
class WalletQuery:
    mon_portefeuille: PortefeuilleType = strawberry.field(resolver=resolve_mon_portefeuille)
    historique_transactions: list[LedgerEntryType] = strawberry.field(resolver=resolve_historique)
    capital_plateforme: PlatformeWalletType = strawberry.field(resolver=resolve_capital_plateforme)
    transactions_plateforme: list[PlatformeTransactionType] = strawberry.field(resolver=resolve_transactions_plateforme)
    finance_admin: FinanceAdminType = strawberry.field(resolver=resolve_finance_admin)