from django.db import models


class TimeStampedModel(models.Model):
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=__import__("uuid").uuid4, editable=False)

    class Meta:
        abstract = True


class CodeParrainModel(models.Model):
    code_parrain = models.CharField(max_length=12, unique=True, blank=True)

    class Meta:
        abstract = True
