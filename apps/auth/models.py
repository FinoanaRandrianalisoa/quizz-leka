from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class RefreshToken(TimeStampedModel):
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    token = models.CharField(max_length=512, unique=True)
    expires_at = models.DateTimeField()
    revoque = models.BooleanField(default=False)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    @property
    def est_valide(self) -> bool:
        return (not self.revoque) and self.expires_at > timezone.now()

    class Meta:
        ordering = ["-cree_le"]


class OTPRequest(TimeStampedModel):
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="otp_requests",
    )
    code_hash = models.CharField(max_length=128)
    destination = models.CharField(max_length=50)
    usage = models.CharField(max_length=40, default="step_up")
    utilise = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
