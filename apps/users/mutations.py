import base64
import mimetypes
import re
import secrets
import string
import uuid
from datetime import date

import strawberry
from django.core.files.base import ContentFile
from strawberry.types import Info

from apps.users.models import Utilisateur
from apps.users.types import UtilisateurType
from common.graphql.errors import NotFoundError, PermissionDeniedError, PseudoAlreadyTakenError, ValidationError
from common.graphql.permissions import get_current_user, require_admin


def generer_code_parrain():
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _sanitize(value: str | None, max_length: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        raise ValidationError("La date de naissance est invalide. Format attendu : AAAA-MM-JJ.")


def _data_url_to_image_file(value: str | None, field_name: str) -> ContentFile | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text.startswith("data:"):
        return None
    match = re.fullmatch(r"data:(image/[a-zA-Z0-9.+-]+);base64,(.+)", text)
    if not match:
        return None
    mime_type, encoded = match.groups()
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    if not payload:
        return None
    extension = mimetypes.guess_extension(mime_type) or ".png"
    return ContentFile(payload, name=f"{field_name}_{uuid.uuid4().hex}{extension}")


def resolve_regenerate_parrain(info: Info) -> UtilisateurType:
    user: Utilisateur = get_current_user(info)
    user.code_parrain = generer_code_parrain()
    user.save()
    return user


@strawberry.input
class UpdateProfilInput:
    pseudo: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_naissance: str | None = None
    telephone: str | None = None
    ville_origine: str | None = None
    photo_profil: str | None = None
    photo_couverture: str | None = None


def resolve_update_profil(info: Info, input: UpdateProfilInput) -> UtilisateurType:
    user = get_current_user(info)

    if input.pseudo:
        value = _sanitize(input.pseudo, 50)
        if not value:
            raise ValidationError("Le nom d'utilisateur ne peut pas être vide.")
        if value.lower() != user.pseudo.lower():
            if Utilisateur.objects.filter(pseudo__iexact=value).exclude(pk=user.pk).exists():
                raise PseudoAlreadyTakenError()
            user.pseudo = value

    if input.first_name is not None:
        user.first_name = _sanitize(input.first_name, 150)
    if input.last_name is not None:
        user.last_name = _sanitize(input.last_name, 150)
    if input.ville_origine is not None:
        user.ville_origine = _sanitize(input.ville_origine, 100)
    if input.telephone is not None:
        telephone = _sanitize(input.telephone, 30)
        if telephone and Utilisateur.objects.filter(telephone__iexact=telephone).exclude(pk=user.pk).exists():
            raise ValidationError("Ce numéro de téléphone est déjà utilisé.")
        user.telephone = telephone or None
    if input.date_naissance is not None:
        user.date_naissance = _parse_date(input.date_naissance)

    profile_image = _data_url_to_image_file(input.photo_profil, "profil")
    cover_image = _data_url_to_image_file(input.photo_couverture, "couverture")
    if profile_image is not None:
        user.photo_profil = profile_image
    if cover_image is not None:
        user.photo_couverture = cover_image

    user.save()
    return user


def resolve_changer_role(info: Info, utilisateur_id: strawberry.ID, role: str) -> UtilisateurType:
    admin = require_admin(info)
    role = (role or "").upper()
    if role not in ("ADMIN", "JOUEUR"):
        raise ValidationError("Rôle invalide. Valeurs autorisées : ADMIN, JOUEUR.")
    try:
        cible = Utilisateur.objects.get(pk=int(utilisateur_id))
    except (Utilisateur.DoesNotExist, ValueError, TypeError):
        raise NotFoundError("Utilisateur introuvable.")
    if cible.pk == admin.pk and role != "ADMIN":
        raise PermissionDeniedError("Vous ne pouvez pas retirer votre propre rôle administrateur.")
    cible.role = role
    cible.is_staff = role == "ADMIN"
    if role != "ADMIN":
        cible.is_superuser = False
    cible.save(update_fields=["role", "is_staff", "is_superuser"])
    return cible


def resolve_desactiver_utilisateur(info: Info, utilisateur_id: strawberry.ID) -> UtilisateurType:
    admin = require_admin(info)
    try:
        cible = Utilisateur.objects.get(pk=int(utilisateur_id))
    except (Utilisateur.DoesNotExist, ValueError, TypeError):
        raise NotFoundError("Utilisateur introuvable.")
    if cible.pk == admin.pk:
        raise PermissionDeniedError("Vous ne pouvez pas désactiver votre propre compte.")
    cible.is_active = False
    cible.save(update_fields=["is_active"])
    return cible


def resolve_activer_utilisateur(info: Info, utilisateur_id: strawberry.ID) -> UtilisateurType:
    admin = require_admin(info)
    try:
        cible = Utilisateur.objects.get(pk=int(utilisateur_id))
    except (Utilisateur.DoesNotExist, ValueError, TypeError):
        raise NotFoundError("Utilisateur introuvable.")
    cible.is_active = True
    cible.save(update_fields=["is_active"])
    return cible


def resolve_supprimer_utilisateur(info: Info, utilisateur_id: strawberry.ID) -> bool:
    admin = require_admin(info)
    try:
        cible = Utilisateur.objects.get(pk=int(utilisateur_id))
    except (Utilisateur.DoesNotExist, ValueError, TypeError):
        raise NotFoundError("Utilisateur introuvable.")
    if cible.pk == admin.pk:
        raise PermissionDeniedError("Vous ne pouvez pas supprimer votre propre compte.")
    cible.delete()
    return True


@strawberry.type
class UsersMutation:
    regenerer_code_parrain: UtilisateurType = strawberry.field(resolver=resolve_regenerate_parrain)
    update_profil: UtilisateurType = strawberry.field(resolver=resolve_update_profil)
    changer_role: UtilisateurType = strawberry.field(resolver=resolve_changer_role)
    desactiver_utilisateur: UtilisateurType = strawberry.field(resolver=resolve_desactiver_utilisateur)
    activer_utilisateur: UtilisateurType = strawberry.field(resolver=resolve_activer_utilisateur)
    supprimer_utilisateur: bool = strawberry.field(resolver=resolve_supprimer_utilisateur)
