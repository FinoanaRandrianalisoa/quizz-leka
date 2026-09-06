from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from apps.users.models import Utilisateur


class EmailBackend(ModelBackend):
    """Authentifie par email ou numéro de téléphone."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        identifiant = email or kwargs.get(self.username_field)
        if identifiant is None:
            return None
        identifiant = str(identifiant).strip()
        try:
            user = Utilisateur.objects.get(Q(email__iexact=identifiant) | Q(telephone__iexact=identifiant))
        except (Utilisateur.DoesNotExist, Utilisateur.MultipleObjectsReturned):
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        try:
            return Utilisateur.objects.get(pk=user_id)
        except Utilisateur.DoesNotExist:
            return None