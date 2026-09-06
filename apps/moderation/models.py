from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from common.models import TimeStampedModel


class Publicite(TimeStampedModel):
    """Emplacements publicitaires (RG-INF / revenus plateforme)."""

    titre = models.CharField(max_length=200)
    contenue = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="publicites/", blank=True, null=True)
    lien = models.URLField(blank=True, default="")
    actif = models.BooleanField(default=False)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return self.titre


class SignalementContenu(TimeStampedModel):
    class Statut(models.TextChoices):
        A_TRAITER = "a_traiter", "À traiter"
        MODERE = "modere", "Modéré"
        REJETE = "rejete", "Rejeté"

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signalements")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    objet_id = models.PositiveIntegerField()
    objet = GenericForeignKey("content_type", "objet_id")
    motif = models.CharField(max_length=200)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.A_TRAITER)

    class Meta:
        ordering = ["-cree_le"]