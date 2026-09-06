from django.contrib import admin

from apps.wallet.models import (
    Portefeuille,
    LedgerEntry,
    PlatformeWallet,
    PlatformeTransaction,
    PortefeuilleEvent,
)


@admin.register(Portefeuille)
class PortefeuilleAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "solde_recharge", "solde_bloque", "solde_gains", "solde_total", "derniere_recharge_le")
    search_fields = ("utilisateur__email", "utilisateur__pseudo")
    readonly_fields = ("pin_hash",)


@admin.register(PlatformeWallet)
class PlatformeWalletAdmin(admin.ModelAdmin):
    list_display = ("id", "capital", "cree_le", "modifie_le")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformeTransaction)
class PlatformeTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "montant", "capital_avant", "capital_apres", "reference", "game_id", "bet_id", "cree_le")
    list_filter = ("type",)
    search_fields = ("reference", "game_id", "bet_id")
    date_hierarchy = "cree_le"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PortefeuilleEvent)
class PortefeuilleEventAdmin(admin.ModelAdmin):
    list_display = ("id", "portefeuille", "type", "ip", "cree_le")
    list_filter = ("type",)
    search_fields = ("portefeuille__utilisateur__pseudo", "ip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "portefeuille", "type", "montant", "solde_apres", "statut", "reference", "cree_le")
    list_filter = ("type", "statut")
    search_fields = ("reference", "idempotency_key")
    date_hierarchy = "cree_le"

    # Grand livre append-only : jamais ajouté ni modifié, jamais supprimé.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False