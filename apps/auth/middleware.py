import uuid

from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from urllib.parse import parse_qs

import jwt
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

from django.conf import settings
from apps.users.models import Utilisateur


def get_user_from_jwt(token: str):
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return AnonymousUser()
    if payload.get("type") != "access":
        return AnonymousUser()
    try:
        return Utilisateur.objects.get(id=payload["sub"])
    except Utilisateur.DoesNotExist:
        return AnonymousUser()


def get_user_from_request(request):
    """Authentifie une requête HTTP via l'en-tête ``Authorization: Bearer <jwt>``."""
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.lower().startswith("bearer "):
        return AnonymousUser()
    return get_user_from_jwt(auth.split(" ", 1)[1].strip())


class JWTAuthMiddleware(BaseMiddleware):
    """Authentifie les connexions WebSocket via le JWT passé en query string."""

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]
        scope["user"] = await database_sync_to_async(get_user_from_jwt)(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)


class CorrelationIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.correlation_id = request.META.get("HTTP_X_CORRELATION_ID") or str(uuid.uuid4())

    def process_response(self, request, response):
        response["X-Correlation-Id"] = getattr(request, "correlation_id", "")
        return response
