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

# Apply CORS middleware for ASGI
from corsheaders.middleware import CorsMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": CorsMiddleware(django_asgi_app),
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
