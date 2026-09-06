from django.db import models
from django.core.exceptions import ValidationError

from common.models import TimeStampedModel


class Theme(TimeStampedModel):
    nom = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, default="")
    icone = models.CharField(max_length=50, blank=True, default="")
    category = models.CharField(max_length=50, default="Quizz")
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Question(TimeStampedModel):
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="questions")
    texte = models.TextField()
    validee = models.BooleanField(default=False)

    class Meta:
        ordering = ["-cree_le"]

    def clean(self):
        reponses = self.reponses.all()
        if reponses.count() < 4:
            raise ValidationError("Une question doit avoir au minimum 4 réponses.")
        correctes = reponses.filter(est_correcte=True).count()
        if correctes != 1:
            raise ValidationError("Une question doit avoir exactement 1 bonne réponse.")


class Reponse(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="reponses")
    texte = models.CharField(max_length=255)
    est_correcte = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
