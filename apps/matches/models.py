from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Match(TimeStampedModel):
    """Une partie entre deux joueurs. RG-GAM."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente d'adversaire"
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"
        ANNULE = "annule", "Annulé"

    class TypeJeu(models.TextChoices):
        CLASSIQUE = "classique", "Classique"
        INTRUS = "intrus", "L'intrus"
        COURSE_LAPIN = "course_lapin", "Course lapin"

    type_jeu = models.CharField(max_length=20, choices=TypeJeu.choices, default=TypeJeu.CLASSIQUE)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_ATTENTE)
    theme = models.ForeignKey(
        "themes.Theme",
        on_delete=models.PROTECT,
        related_name="matchs",
    )
    mise = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    mise_proposee_invite = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    score_cible = models.PositiveIntegerField(default=8)
    joueur_hote = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="matchs_hotes",
    )
    joueur_invite = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="matchs_invites",
    )
    vainqueur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matchs_gagnes",
    )
    score_hote = models.PositiveIntegerField(default=0)
    score_invite = models.PositiveIntegerField(default=0)
    tour_actuel = models.PositiveIntegerField(default=0)
    commence_le = models.DateTimeField(null=True, blank=True)
    termine_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"Match #{self.pk} ({self.theme})"

    @property
    def complet(self) -> bool:
        return self.joueur_invite is not None

    @property
    def mise_proposee_hote(self):
        return self.mise

    @property
    def mise_effective(self):
        """Mise effectivement engagée : MIN(mise_hôte, mise_invité)."""
        invite = self.mise_proposee_invite if self.mise_proposee_invite is not None else self.mise
        if invite <= 0:
            return self.mise
        return min(self.mise, invite)

    @property
    def premier_tiers_atteint(self) -> bool:
        seuil = max(1, self.score_cible // 3)
        return max(self.score_hote, self.score_invite) >= seuil


class Tour(TimeStampedModel):
    """Un tour de question dans un match."""

    class Statut(models.TextChoices):
        EN_COURS = "en_cours", "En cours"
        TERMINE = "termine", "Terminé"

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="tours")
    numero = models.PositiveIntegerField()
    question = models.ForeignKey("themes.Question", on_delete=models.PROTECT, related_name="tours")
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.EN_COURS)

    class Meta:
        unique_together = [("match", "numero")]
        ordering = ["numero"]


class ReponseTour(TimeStampedModel):
    """Réponse soumise par un joueur à un tour."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="reponses")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reponses_tours")
    reponse = models.ForeignKey("themes.Reponse", on_delete=models.PROTECT, related_name="+")
    correcte = models.BooleanField(default=False)
    duree_ms = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("tour", "utilisateur")]


class Participation(TimeStampedModel):
    """Participation d'un joueur à une partie (compteurs de profil)."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="participations")
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="participations")
    score_final = models.PositiveIntegerField(default=0)
    vainqueur = models.BooleanField(default=False)

    class Meta:
        unique_together = [("match", "utilisateur")]