import logging
import os
import re

from django.core.asgi import get_asgi_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()
logger.info("ASGI application initialized. Django app ready — template render should be available.")

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from apps.auth.middleware import JWTAuthMiddleware
from config.routing import websocket_urlpatterns

# En-têtes CORS communs à la prévol (OPTIONS) et aux réponses normales.
# On écho l'origine réelle — identique au comportement de django-cors-headers
# quand `CORS_ALLOW_CREDENTIALS=True`.
_CORS_HEADERS = [
    (b"access-control-allow-credentials", b"true"),
    (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
    (b"access-control-allow-headers", b"content-type, authorization, x-requested-with, accept, origin, x-csrftoken"),
    (b"access-control-expose-headers", b"x-request-id, x-correlation-id"),
    (b"access-control-max-age", b"86400"),
    (b"vary", b"Origin"),
]


def _correspond_au_pattern(origin: str, pattern: str) -> bool:
    try:
        return bool(re.match(pattern, origin))
    except re.error:
        return False


# Custom ASGI CORS middleware
class ASGICORSMiddleware:
    """Ajoute les en-têtes CORS pour les origines autorisées.

    Complète django-cors-headers (qui ne court que la pile HTTP de Django) :
    la prévol (OPTIONS) est ici traitée en une seule fois. Les origines
    autorisées suivent exactement les règles des settings :
      - `CORS_ALLOW_ALL_ORIGINS=True` → tout origine ;
      - `CORS_ALLOWED_ORIGINS` (comparaison exacte, après normalisation) ;
      - `CORS_ALLOWED_ORIGIN_REGEXES` (Vercel, Railway, …).
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def origine_autorisee(origin: str) -> bool:
        if not origin:
            return False
        from django.conf import settings

        if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
            return True
        origine_normale = origin.rstrip("/")
        if origine_normale in [str(o).rstrip("/") for o in getattr(settings, "CORS_ALLOWED_ORIGINS", [])]:
            return True
        return any(
            _correspond_au_pattern(origin, pat)
            for pat in (getattr(settings, "CORS_ALLOWED_ORIGIN_REGEXES", None) or [])
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers_dict = dict(scope.get("headers", []))
        origin = headers_dict.get(b"origin")
        origin = origin.decode() if origin else ""

        # Prévol (OPTIONS) : on répond directement, sans passer par Django.
        if scope.get("method") == "OPTIONS":
            if self.origine_autorisee(origin):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"access-control-allow-origin", origin.encode()), *_CORS_HEADERS],
                    }
                )
                await send({"type": "http.response.body", "body": b""})
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": b'{"detail":"Origin forbidden"}'})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                if origin and self.origine_autorisee(origin):
                    headers[b"access-control-allow-origin"] = origin.encode()
                    headers[b"access-control-allow-credentials"] = b"true"
                    headers.setdefault(b"vary", b"Origin")
                message["headers"] = list(headers.items())
            await send(message)

        return await self.app(scope, receive, send_wrapper)

application = ProtocolTypeRouter(
    {
        "http": ASGICORSMiddleware(django_asgi_app),
        "websocket": JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
