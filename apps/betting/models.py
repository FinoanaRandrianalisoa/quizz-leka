from decimal import Decimal

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Pari(TimeStampedModel):
    """Paris spectateurs en direct sur un match (RG-BET)."""

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        GAGNE = "gagne", "Gagné"
        PERDU = "perdu", "Perdu"
        REMBOURSE = "rembourse", "Remboursé"

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="paris")
    match = models.ForeignKey("matches.Match", on_delete=models.CASCADE, related_name="paris")
    joueur_pari = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    montant = models.DecimalField(max_digits=18, decimal_places=2)
    cote = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("2.00"))
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_COURS)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-cree_le"]

    @property
    def gain_potentiel(self):
        return None if self.statut != self.Statut.EN_COURS else (self.montant * self.cote)


class SignalFraude(TimeStampedModel):
    """Piste d'audit pour les suspicions de fraude/collusion (post-MVP)."""

    class TypeAnomalie(models.TextChoices):
        COLLUSION = "collusion", "Collusion"
        AUTOPARI = "autopari", "Auto-pari"
        TEMPS_REPONSE = "temps_reponse", "Temps de réponse anormal"
        MARTELAGE = "martelage", "Martelage (rate limited)"

    type_anomalie = models.CharField(max_length=30, choices=TypeAnomalie.choices)
    match = models.ForeignKey("matches.Match", on_delete=models.SET_NULL, null=True, blank=True)
    utilisateurs = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True)
    score_suspicion = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)
    traite = models.BooleanField(default=False)

    class Meta:
        ordering = ["-cree_le"]