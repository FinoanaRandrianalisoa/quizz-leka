import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "unsafe-default-secret-key"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "quizz-leka.onrender.com", ".onrender.com"]),
    CORS_ALLOWED_ORIGINS=(
        list,
        [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8443",
            "https://frontend-quizz-leka-hkq7.vercel.app",
        ],
    ),
    DATABASE_URL=(
        str,
        "postgres://mahafeno:antso0201@postgresql-mahafeno.alwaysdata.net:5432/mahafeno_quizz",
    ),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    CELERY_BROKER_URL=(str, "redis://localhost:6379/1"),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

# fusionne les hôtes autorisés depuis l'environnement avec nos hôtes par défaut
ALLOWED_HOSTS = list(
    set(
        env.list("ALLOWED_HOSTS", default=[])
        + ["localhost", "127.0.0.1", "quizz-leka.onrender.com", ".onrender.com"]
    )
)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "strawberry_django",
    "channels",
    "django_celery_beat",
    "apps.users.apps.UsersConfig",
    "apps.auth.apps.AuthConfig",
    "apps.wallet",
    "apps.matches",
    "apps.betting",
    "apps.themes.apps.ThemesConfig",
    "apps.quiz_global.apps.QuizGlobalConfig",
    "apps.social",
    "apps.discussions",
    "apps.moderation",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Doit impérativement être le premier middleware
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.auth.middleware.CorrelationIdMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/quizz",
    )
}

AUTH_USER_MODEL = "users.Utilisateur"

AUTHENTICATION_BACKENDS = [
    "apps.auth.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Indian/Antananarivo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATA_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024
)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024
)

# --- CORS & CSRF ---
# Fusion des origines autorisées dans env + valeurs explicites
RAW_CORS_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = list(
    set(
        RAW_CORS_ORIGINS
        + [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8443",
            "https://frontend-quizz-leka-hkq7.vercel.app",
        ]
    )
)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False

# Expression régulière pour valider Vercel dynamiquement (Production + Previews)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https:\/\/.*\.vercel\.app$",
]

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# Domaines de confiance pour les requêtes POST / CSRF
CSRF_TRUSTED_ORIGINS = [
    "https://frontend-quizz-leka-hkq7.vercel.app",
    "https://*.vercel.app",
    "https://quizz-leka.onrender.com",
]

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL")]},
    }
}

# Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# Celery
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_TASK_QUEUES = {
    "payments": {"exchange": "payments", "routing_key": "payments"},
    "notifications": {
        "exchange": "notifications",
        "routing_key": "notifications",
    },
    "default": {"exchange": "default", "routing_key": "default"},
    "matches": {"exchange": "matches", "routing_key": "matches"},
}
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}

# JWT maison
JWT_ACCESS_TTL = env.int("JWT_ACCESS_TTL", default=900)
JWT_REFRESH_TTL = env.int("JWT_REFRESH_TTL", default=2592000)
JWT_SECRET = env("SECRET_KEY")

# Compte admin créé automatiquement au lancement (idempotent)
BOOTSTRAP_ADMIN_ENABLED = env.bool("BOOTSTRAP_ADMIN_ENABLED", default=True)
BOOTSTRAP_ADMIN_EMAIL = env("BOOTSTRAP_ADMIN_EMAIL", default="admin@quizz.mg")
BOOTSTRAP_ADMIN_PASSWORD = env("BOOTSTRAP_ADMIN_PASSWORD", default="Admin123!")
BOOTSTRAP_ADMIN_PSEUDO = env("BOOTSTRAP_ADMIN_PSEUDO", default="Admin")

# Mobile Money
MOBILE_MONEY_WEBHOOK_SECRET = env("MOBILE_MONEY_WEBHOOK_SECRET", default="")
MVOLA_API_KEY = env("MVOLA_API_KEY", default="")
ORANGE_MONEY_API_KEY = env("ORANGE_MONEY_API_KEY", default="")
AIRTEL_MONEY_API_KEY = env("AIRTEL_MONEY_API_KEY", default="")

# OTP
OTP_PROVIDER_SID = env("OTP_PROVIDER_SID", default="")
OTP_PROVIDER_TOKEN = env("OTP_PROVIDER_TOKEN", default="")
OTP_TTL_SECONDS = 300

# Commission plateforme (pourcentage)
COMMISSION_RATE = env.float("COMMISSION_RATE", default=0.20)

# Portefeuille DEMO — fonds virtuels, non retirables
DEMO_INITIAL_BALANCE = env.int("DEMO_INITIAL_BALANCE", default=1_000_000)
DEMO_RECHARGE_AMOUNT = env.int("DEMO_RECHARGE_AMOUNT", default=1_000_000)
DEMO_RECHARGE_LIMIT = env.int("DEMO_RECHARGE_LIMIT", default=1)  # recharges / jour
DEMO_STAKE_MIN = env.int("DEMO_STAKE_MIN", default=100)
# Commission définitive appliquée au règlement : 20 % de la mise effective de chaque participant.
COMMISSION_DEMO_RATE = env.float("COMMISSION_DEMO_RATE", default=0.20)

# PIN portefeuille (4 chiffres, distinct du mot de passe de connexion)
WALLET_PIN_LENGTH = 4
WALLET_PIN_UNLOCK_DURATION = env.int(
    "WALLET_PIN_UNLOCK_DURATION", default=300
)  # secondes
WALLET_PIN_MAX_ATTEMPTS = env.int("WALLET_PIN_MAX_ATTEMPTS", default=5)
WALLET_PIN_LOCK_DURATION = env.int(
    "WALLET_PIN_LOCK_DURATION", default=300
)  # secondes

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}