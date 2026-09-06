import datetime as dt
import uuid

import jwt
from django.conf import settings
from django.utils import timezone

from apps.auth.models import RefreshToken


def _payload(user, token_type: str, ttl: int):
    now = timezone.now()
    return {
        "sub": str(user.id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }


def generate_access_token(user) -> str:
    return jwt.encode(_payload(user, "access", settings.JWT_ACCESS_TTL), settings.JWT_SECRET, algorithm="HS256")


def generate_refresh_token(user) -> str:
    raw = jwt.encode(_payload(user, "refresh", settings.JWT_REFRESH_TTL), settings.JWT_SECRET, algorithm="HS256")
    RefreshToken.objects.create(utilisateur=user, token=raw, expires_at=timezone.now() + dt.timedelta(seconds=settings.JWT_REFRESH_TTL))
    return raw


def decode_token(token: str, expected_type: str = "access") -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
