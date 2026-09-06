from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Ville(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Message(TimeStampedModel):
    """Message d'un salon de discussion par ville (RG-DIS)."""

    ville = models.ForeignKey(Ville, on_delete=models.CASCADE, related_name="messages")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages")
    contenu = models.TextField()

    class Meta:
        ordering = ["cree_le"]


class MessageAmi(TimeStampedModel):
    """Message privé entre deux amis."""

    expediteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages_amis_envoyes")
    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages_amis_recus")
    contenu = models.TextField()
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ["cree_le"]