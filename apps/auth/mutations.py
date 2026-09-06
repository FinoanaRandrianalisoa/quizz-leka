import base64
import hashlib
import mimetypes
import re
import secrets
import string
import uuid
from datetime import date, timedelta

import strawberry
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from strawberry.types import Info

from apps.auth.jwt import generate_access_token, generate_refresh_token, decode_token
from apps.auth.models import RefreshToken, OTPRequest
from apps.auth.otp import generate_otp, send_otp
from apps.discussions.models import Ville
from apps.users.models import Utilisateur
from apps.users.types import UtilisateurType
from common.graphql.errors import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RevokedRefreshTokenError,
    InvalidOtpError,
    EmailAlreadyTakenError,
    PseudoAlreadyTakenError,
    ValidationError,
)
from common.graphql.permissions import get_current_user


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _sanitize_text(value: str | None, max_length: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text


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


@strawberry.type
class AuthPayload:
    access_token: str
    user_id: str
    refresh_token_set: bool
    utilisateur: UtilisateurType


@strawberry.type
class LoginPayload(AuthPayload):
    pass


@strawberry.input
class RegisterInput:
    email: str = ""
    pseudo: str
    password: str
    code_parent: str | None = None
    ville_origine: str = ""
    first_name: str = ""
    last_name: str = ""
    date_naissance: str = ""
    telephone: str = ""
    photo_profil: str = ""
    photo_couverture: str = ""
    fingerprint: str = ""


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        raise ValidationError("La date de naissance est invalide. Format attendu : AAAA-MM-JJ.")


def resolve_register(info: Info, input: RegisterInput) -> AuthPayload:
    email = _sanitize_text(input.email, 254).lower() or None
    telephone = _sanitize_text(input.telephone, 30) or None
    if email and Utilisateur.objects.filter(email__iexact=email).exists():
        raise EmailAlreadyTakenError()
    if Utilisateur.objects.filter(pseudo__iexact=input.pseudo).exists():
        raise PseudoAlreadyTakenError()
    if telephone and Utilisateur.objects.filter(telephone__iexact=telephone).exists():
        raise ValidationError("Ce numéro de téléphone est déjà utilisé.")
    if not email and not telephone:
        raise ValidationError("Un email ou un numéro de téléphone est requis.")

    user = Utilisateur(
        username=(email or telephone or input.pseudo).lower(),
        email=email,
        pseudo=input.pseudo,
        ville_origine=_sanitize_text(input.ville_origine, 100),
        first_name=_sanitize_text(input.first_name, 150),
        last_name=_sanitize_text(input.last_name, 150),
        telephone=telephone or None,
        date_naissance=_parse_date(input.date_naissance),
    )
    profile_image = _data_url_to_image_file(input.photo_profil, "profil")
    cover_image = _data_url_to_image_file(input.photo_couverture, "couverture")
    if profile_image is not None:
        user.photo_profil = profile_image
    if cover_image is not None:
        user.photo_couverture = cover_image
    if input.code_parent:
        user.code_parent = input.code_parent.upper()
    user.set_password(input.password)
    user.save()

    ville_nom = (input.ville_origine or "").strip()
    if ville_nom:
        ville, _ = Ville.objects.get_or_create(
            nom=ville_nom,
            defaults={"slug": ville_nom.lower().replace(" ", "-")},
        )
        if not ville.slug:
            ville.slug = ville_nom.lower().replace(" ", "-")
            ville.save(update_fields=["slug"])

    access = generate_access_token(user)
    generate_refresh_token(user)
    return AuthPayload(
        access_token=access,
        user_id=str(user.id),
        refresh_token_set=True,
        utilisateur=user,
    )


def resolve_login(info: Info, email: str, password: str) -> AuthPayload:
    user = authenticate(request=info.context.request, email=email, password=password)
    if user is None:
        raise InvalidCredentialsError()
    user.en_ligne = True
    user.save(update_fields=["en_ligne"])
    access = generate_access_token(user)
    generate_refresh_token(user)
    return AuthPayload(
        access_token=access,
        user_id=str(user.id),
        refresh_token_set=True,
        utilisateur=user,
    )


def resolve_refresh(info: Info, refresh_token: str) -> AuthPayload:
    try:
        payload = decode_token(refresh_token, "refresh")
    except Exception:
        raise InvalidRefreshTokenError()
    try:
        stored = RefreshToken.objects.get(token=refresh_token)
    except RefreshToken.DoesNotExist:
        raise InvalidRefreshTokenError()
    if not stored.est_valide:
        raise RevokedRefreshTokenError()
    # Rotation
    stored.revoque = True
    stored.save(update_fields=["revoque"])
    user = stored.utilisateur
    access = generate_access_token(user)
    generate_refresh_token(user)
    return AuthPayload(
        access_token=access,
        user_id=str(user.id),
        refresh_token_set=True,
        utilisateur=user,
    )


def resolve_logout(info: Info, refresh_token: str) -> bool:
    try:
        stored = RefreshToken.objects.get(token=refresh_token)
    except RefreshToken.DoesNotExist:
        return True
    stored.revoque = True
    stored.save(update_fields=["revoque"])
    user = stored.utilisateur
    if user.en_ligne:
        user.en_ligne = False
        user.save(update_fields=["en_ligne"])
    return True


@strawberry.type
class VerifyOtpPayload:
    token: str
    expires_in: int


def resolve_request_otp(info: Info, destination: str) -> bool:
    user = get_current_user(info)
    code = generate_otp()
    OTPRequest.objects.create(
        utilisateur=user,
        code_hash=_hash(code),
        destination=destination,
        usage="step_up",
        expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
        ip=getattr(info.context.request, "META", {}).get("REMOTE_ADDR"),
    )
    send_otp(destination, code)
    return True


def resolve_verify_otp(info: Info, destination: str, code: str) -> VerifyOtpPayload:
    user = get_current_user(info)
    latest = (
        OTPRequest.objects.filter(utilisateur=user, destination=destination, usage="step_up")
        .order_by("-cree_le")
        .first()
    )
    if not latest or latest.utilise or latest.expires_at < timezone.now() or not secrets.compare_digest(latest.code_hash, _hash(code)):
        raise InvalidOtpError()
    latest.utilise = True
    latest.save(update_fields=["utilise"])
    payload = {
        "sub": str(user.id),
        "type": "stepup",
        "exp": int((timezone.now() + timedelta(seconds=300)).timestamp()),
    }
    import jwt
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return VerifyOtpPayload(token=token, expires_in=300)


@strawberry.type
class AuthMutation:
    register: AuthPayload = strawberry.field(resolver=resolve_register)
    login: AuthPayload = strawberry.field(resolver=resolve_login)
    refresh: AuthPayload = strawberry.field(resolver=resolve_refresh, name="refreshToken")
    logout: bool = strawberry.field(resolver=resolve_logout)
    request_otp: bool = strawberry.field(resolver=resolve_request_otp)
    verify_otp: VerifyOtpPayload = strawberry.field(resolver=resolve_verify_otp, name="verifyOtp")

