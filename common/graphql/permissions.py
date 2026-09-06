from strawberry.types import Info

from common.graphql.errors import PermissionDeniedError


def get_current_user(info: Info):
    """Retourne l'utilisateur authentifié ou lève PERMISSION_DENIED."""
    user = info.context.request.user
    if getattr(user, "is_anonymous", True):
        raise PermissionDeniedError("Authentification requise.")
    return user


def require_admin(info: Info):
    """Utilisateur authentifié avec le rôle ADMIN (ou superuser Django)."""
    user = get_current_user(info)
    if getattr(user, "role", None) != "ADMIN" and not getattr(user, "is_superuser", False):
        raise PermissionDeniedError("Réservé aux administrateurs.")
    return user