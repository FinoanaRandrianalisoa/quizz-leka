from .base import *  # noqa: F401,F403

# Environnement de test : rapide, déterministe, sans services externes.
DEBUG = False
SECRET_KEY = "secret-de-test"
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

GRAPHQL_INTROSPECTION_ENABLED = True
OTP_TTL_SECONDS = 300
BOOTSTRAP_ADMIN_ENABLED = False