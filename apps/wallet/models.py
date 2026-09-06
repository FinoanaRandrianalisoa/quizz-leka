from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Portefeuille(models.Model):
    """Portefeuille DEMO d'un utilisateur.

    Solde disponible : `solde_recharge` (fonds virtuels utilisables, non retirables).
    Solde bloqué    : `solde_bloque` (réservé pour une partie ou un pari en attente/en cours).
    Gains           : `solde_gains`  (origine des fonds distincte, toujours virtuels).
    """

    utilisateur = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portefeuille",
    )
    solde_recharge = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    solde_bloque = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    solde_gains = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    # Sécurité PIN (4 chiffres, distinct du mot de passe de connexion)
    pin_hash = models.CharField(max_length=255, blank=True, default="")
    is_locked = models.BooleanField(default=True)
    unlocked_until = models.DateTimeField(null=True, blank=True)
    pin_failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    derniere_recharge_le = models.DateField(null=True, blank=True)

    modifie_le = models.DateTimeField(auto_now=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Portefeuille"
        verbose_name_plural = "Portefeuilles"

    @property
    def solde_disponible(self):
        return self.solde_recharge

    @property
    def solde_total(self):
        return self.solde_recharge + self.solde_bloque + self.solde_gains

    @property
    def pin_defini(self) -> bool:
        return bool(self.pin_hash)


class PlatformeWallet(TimeStampedModel):
    """Capital de la plateforme — portefeuille indépendant des joueurs."""

    capital = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Capital plateforme"
        verbose_name_plural = "Capital plateforme"

    @classmethod
    def singleton(cls) -> "PlatformeWallet":
        wallet, _ = cls.objects.get_or_create(pk=1)
        return wallet


class PlatformeTransaction(models.Model):
    """Mouvement du capital plateforme — append-only, jamais supprimé."""

    class Type(models.TextChoices):
        COMMISSION = "commission", "Commission plateforme"
        AJUSTEMENT = "ajustement", "Ajustement compensatoire"

    platforme = models.ForeignKey(
        PlatformeWallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    montant = models.DecimalField(max_digits=18, decimal_places=2)
    capital_avant = models.DecimalField(max_digits=18, decimal_places=2)
    capital_apres = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=128, blank=True, default="")
    game_id = models.CharField(max_length=100, blank=True, default="")
    bet_id = models.CharField(max_length=100, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.get_type_display()} {self.montant}"


class PortefeuilleEvent(models.Model):
    """Journal des événements de sécurité du portefeuille (PIN).

    Le PIN lui-même n'est jamais stocké ici ni dans les logs/GraphQL.
    """

    class Type(models.TextChoices):
        PIN_FAILED = "pin_failed", "PIN incorrect"
        WALLET_UNLOCKED = "wallet_unlocked", "Portefeuille déverrouillé"
        WALLET_LOCKED = "wallet_locked", "Portefeuille verrouillé"
        PIN_SET = "pin_set", "PIN défini"
        PIN_CHANGED = "pin_changed", "PIN modifié"

    portefeuille = models.ForeignKey(Portefeuille, on_delete=models.PROTECT, related_name="evenements")
    type = models.CharField(max_length=30, choices=Type.choices)
    metadata = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cree_le"]


class LedgerEntry(TimeStampedModel):
    """Grand livre append-only — source de vérité des mouvements financiers."""

    class Type(models.TextChoices):
        DEPOT = "depot", "Dépôt"
        RETRAIT = "retrait", "Retrait"
        DEMO_INITIAL_CREDIT = "demo_credit_initial", "Crédit initial DEMO"
        DEMO_RECHARGE = "demo_recharge", "Recharge DEMO"
        MISE_BLOQUEE = "mise_bloquee", "Mise réservée"
        MISE_ENGAGEE = "mise_engagee", "Mise engagée"
        MISE_LIBEREE = "mise_liberee", "Mise libérée"
        GAIN = "gain", "Gain"
        COMMISSION = "commission", "Commission plateforme"
        REMBOURSEMENT = "remboursement", "Remboursement"
        PERTE = "perte", "Perte pari"
        TRANSFERT = "transfert", "Transfert DEMO"

    class Statut(models.TextChoices):
        PENDING = "pending", "En attente"
        SUCCES = "succes", "Succès"
        ECHOUE = "echoue", "Échoué"

    portefeuille = models.ForeignKey(Portefeuille, on_delete=models.PROTECT, related_name="ledger_entries")
    type = models.CharField(max_length=25, choices=Type.choices)
    montant = models.DecimalField(max_digits=18, decimal_places=2)
    solde_avant = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    solde_apres = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    bloque_avant = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    bloque_apres = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.CharField(max_length=100, blank=True, default="")
    reference = models.CharField(max_length=128, blank=True, default="")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PENDING)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=150, blank=True, default="", db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-cree_le"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                name="uniq_ledger_idem",
                condition=models.Q(idempotency_key__gt=""),
            )
        ]