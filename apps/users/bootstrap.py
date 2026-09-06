import logging

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def _tables_ready() -> bool:
    try:
        return "users_utilisateur" in connection.introspection.table_names()
    except (OperationalError, ProgrammingError):
        return False


def ensure_bootstrap_admin() -> None:
    """Crée (idempotent) le compte admin de lancement si les tables existent."""
    if not getattr(settings, "BOOTSTRAP_ADMIN_ENABLED", True):
        return
    if not _tables_ready():
        return

    from apps.users.models import Utilisateur

    email = (getattr(settings, "BOOTSTRAP_ADMIN_EMAIL", "") or "").strip().lower()
    password = getattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "") or ""
    pseudo = (getattr(settings, "BOOTSTRAP_ADMIN_PSEUDO", "") or "Admin").strip()
    if not email or not password:
        logger.warning("Bootstrap admin ignoré : email ou mot de passe manquant.")
        return

    user = Utilisateur.objects.filter(email__iexact=email).first()
    if user is None:
        if Utilisateur.objects.filter(pseudo__iexact=pseudo).exists():
            pseudo = f"{pseudo}Admin"
        user = Utilisateur(
            username=email,
            email=email,
            pseudo=pseudo,
            role="ADMIN",
            is_staff=True,
            is_superuser=True,
            email_verifie=True,
        )
        user.set_password(password)
        user.save()
        logger.info("Compte admin bootstrap créé : %s", email)
        return

    changed = False
    if user.role != "ADMIN":
        user.role = "ADMIN"
        changed = True
    if not user.is_staff:
        user.is_staff = True
        changed = True
    if not user.is_superuser:
        user.is_superuser = True
        changed = True
    if user.username != email:
        user.username = email
        changed = True
    if changed:
        user.save()
        logger.info("Compte existant promu admin bootstrap : %s", email)
