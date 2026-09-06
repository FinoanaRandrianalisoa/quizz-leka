from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import Utilisateur
from apps.wallet.models import Portefeuille
from apps.wallet.services import crediter_demo_initial


@receiver(post_save, sender=Utilisateur)
def creer_portefeuille(sender, instance, created, **kwargs):
    if created:
        portefeuille = Portefeuille.objects.create(utilisateur=instance)
        # Dotation DEMO initiale et idempotente (+1 000 000 Ar virtuels).
        try:
            crediter_demo_initial(portefeuille)
        except Exception:  # pragma: no cover — jamais bloquer l'inscription sur le crédit
            pass
