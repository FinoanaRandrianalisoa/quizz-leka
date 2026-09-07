import os
import logging

from django.core.asgi import get_asgi_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()
logger.info("ASGI application initialized. Django app ready — template render should be available.")

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402
from apps.auth.middleware import JWTAuthMiddleware  # noqa: E402

# Custom ASGI CORS middleware
class ASGICORSMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Handle CORS preflight and add headers
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = dict(message.get("headers", []))
                    
                    # Add CORS headers
                    origin = None
                    for header_name, header_value in headers.items():
                        if header_name.lower() == b"origin":
                            origin = header_value.decode()
                            break
                    
                    if origin:
                        # Check if origin is allowed
                        from django.conf import settings
                        allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
                        if origin in allowed_origins or any(allowed in origin for allowed in allowed_origins):
                            headers[b"access-control-allow-origin"] = origin.encode()
                            headers[b"access-control-allow-credentials"] = b"true"
                            headers[b"access-control-allow-methods"] = b"GET, POST, PUT, PATCH, DELETE, OPTIONS"
                            headers[b"access-control-allow-headers"] = b"content-type, authorization, x-requested-with, accept, origin"
                    
                    message["headers"] = list(headers.items())
                await send(message)
            
            return await self.app(scope, receive, send_wrapper)
        else:
            return await self.app(scope, receive, send)

application = ProtocolTypeRouter(
    {
        "http": ASGICORSMiddleware(django_asgi_app),
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
