from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://localhost:8443",
    "http://127.0.0.1:8443",
]
# Cookies SameSite=None/credentials — les domaines front/back sont séparés.
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
GRAPHQL_INTROSPECTION_ENABLED = True

# In development, Redis may not be available locally. Keep the WebSocket and
# cache layer local-memory based so the game and challenge flow keep working
# without an external Redis server.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "quizz-local-cache",
    }
}
