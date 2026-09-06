import strawberry
import strawberry_django

from apps.wallet import models, services


@strawberry_django.type(models.Portefeuille)
class PortefeuilleType:
    id: strawberry.auto
    solde_recharge: strawberry.auto
    solde_bloque: strawberry.auto
    solde_gains: strawberry.auto

    @strawberry.field
    def solde_total(self) -> str:
        return str(self.solde_recharge + self.solde_bloque + self.solde_gains)

    @strawberry.field
    def solde_disponible(self) -> str:
        return str(self.solde_recharge)

    @strawberry.field
    def solde_bloque_total(self) -> str:
        return str(self.solde_bloque)

    @strawberry.field
    def solde_gains_total(self) -> str:
        return str(self.solde_gains)

    @strawberry.field
    def pin_defini(self) -> bool:
        return self.pin_defini

    @strawberry.field
    def portefeuille_deverrouille(self) -> bool:
        return services.est_deverrouille(self)

    @strawberry.field
    def mode_demo(self) -> bool:
        return True

    @strawberry.field
    def recharge_demo_disponible(self) -> bool:
        aujourd_hui = timezone_localdate()
        limite = int(settings_demo_recharge_limit())
        count = self.ledger_entries.filter(
            type=models.LedgerEntry.Type.DEMO_RECHARGE,
            cree_le__date=aujourd_hui,
        ).count()
        return count < limite


def settings_demo_recharge_limit():
    from django.conf import settings
    return settings.DEMO_RECHARGE_LIMIT


def timezone_localdate():
    from django.utils import timezone
    return timezone.localdate()


@strawberry_django.type(models.LedgerEntry)
class LedgerEntryType:
    id: strawberry.auto
    type: strawberry.auto
    montant: strawberry.auto
    solde_avant: strawberry.auto
    solde_apres: strawberry.auto
    reference: strawberry.auto
    statut: strawberry.auto
    cree_le: strawberry.auto


@strawberry.type
class PlatformeWalletType:
    capital: str

    @classmethod
    def from_model(cls, wallet: models.PlatformeWallet) -> "PlatformeWalletType":
        return cls(capital=str(wallet.capital))


@strawberry_django.type(models.PlatformeTransaction)
class PlatformeTransactionType:
    id: strawberry.auto
    type: strawberry.auto
    montant: strawberry.auto
    capital_avant: strawberry.auto
    capital_apres: strawberry.auto
    reference: strawberry.auto
    game_id: strawberry.auto
    bet_id: strawberry.auto
    cree_le: strawberry.auto


@strawberry.type
class FinanceAdminType:
    nombre_joueurs: int
    solde_total_distribue: str
    solde_detenu_par_joueurs: str
    total_mise: str
    total_gagne: str
    total_perdu: str
    total_commissions: str
    capital_plateforme: str
    nombre_matchs: int
    mise_moyenne: str
    meilleur_joueur: "FinanceAdminJoueurType | None"
    meilleur_generateur_commissions: "FinanceAdminJoueurType | None"
    nombre_paris: int


@strawberry.type
class FinanceAdminJoueurType:
    id: strawberry.ID
    pseudo: str
    valeur: str
    detail: str | None = None