from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Publication(TimeStampedModel):
    class Statut(models.TextChoices):
        PUBLIE = "publie", "Publié"
        SUPPRIME = "supprime", "Supprimé (modération)"

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="publications")
    texte = models.TextField()
    image = models.ImageField(upload_to="publications/", blank=True, null=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PUBLIE)
    lien_type = models.CharField(max_length=30, blank=True, default="")
    reference_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-cree_le"]

    @property
    def nombre_reactions(self) -> int:
        return self.reactions.count()

    @property
    def nombre_commentaires(self) -> int:
        return self.commentaires.count()


class Commentaire(TimeStampedModel):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="commentaires")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="commentaires")
    texte = models.TextField()

    class Meta:
        ordering = ["cree_le"]


class Reaction(TimeStampedModel):
    class Type(models.TextChoices):
        JAIME = "jaime", "J'aime"

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="reactions")
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reactions")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.JAIME)

    class Meta:
        unique_together = [("publication", "auteur")]


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        DEFI_RECU = "defi_recu", "Défi reçu"
        DEFI_ACCEPTE = "defi_accepte", "Défi accepté"
        AMI_ACCEPTE = "ami_accepte", "Demande acceptée"
        SYSTEME = "systeme", "Système"

    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    expediteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications_envoyees",
    )
    type = models.CharField(max_length=30, choices=Type.choices, default=Type.SYSTEME)
    titre = models.CharField(max_length=120)
    message = models.TextField()
    reference_id = models.PositiveBigIntegerField(default=0)
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ["-cree_le"]


class DemandeAmi(TimeStampedModel):
    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        ACCEPTEE = "acceptee", "Acceptée"
        REFUSEE = "refusee", "Refusée"

    demandeur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demandes_envoyees")
    receveur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demandes_recues")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)

    class Meta:
        unique_together = [("demandeur", "receveur")]
        ordering = ["-cree_le"]