import os
from pathlib import Path
import sys

import dj_database_url
from django.contrib.messages import constants as messages_constants
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(env_path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env_to_bool(name, default=False):
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def env_to_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


load_env_file(BASE_DIR / ".env")

SECRET_KEY_DEFAUT_DEV = "intranet-dges-dev-secret-key-change-me"

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    os.getenv("DJANGO_SECRET_KEY", SECRET_KEY_DEFAUT_DEV),
)
DEBUG = env_to_bool("DEBUG", env_to_bool("DJANGO_DEBUG", True))

# Echec bruyant plutot que demarrage silencieux avec une cle connue : sans ce
# controle, un `.env` absent ou mal monte lancait l'application avec la cle
# d'exemple, et personne ne s'en apercevait.
if not DEBUG and SECRET_KEY == SECRET_KEY_DEFAUT_DEV:
    raise ImproperlyConfigured(
        "SECRET_KEY porte encore la valeur de developpement alors que DEBUG=0. "
        "Definissez une cle longue et aleatoire dans .env avant de demarrer en production."
    )
ALLOWED_HOSTS = env_to_list(
    "ALLOWED_HOSTS",
    os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"),
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "dashboard",
    "visitors",
    "tasks",
    "documents",
    "meetings",
    "diplomas",
    "courriers",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Doit suivre l'authentification : s'appuie sur request.user.
    "core.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "intranet_dges.urls"

# Django nomme le niveau d'erreur "error" alors que Bootstrap attend "danger" :
# sans cette table, les messages d'erreur ne s'affichent pas en rouge.
MESSAGE_TAGS = {
    messages_constants.ERROR: "danger",
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.application_context",
            ],
        },
    }
]

WSGI_APPLICATION = "intranet_dges.wsgi.application"

database_url = os.getenv("DATABASE_URL")
postgres_db = os.getenv("POSTGRES_DB")
postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_host = os.getenv("POSTGRES_HOST", "db")
postgres_port = os.getenv("POSTGRES_PORT", "5432")
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
RUNNING_IN_DOCKER = Path("/.dockerenv").exists()
USE_POSTGRES = env_to_bool("USE_POSTGRES", RUNNING_IN_DOCKER)

if RUNNING_TESTS:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test_db.sqlite3",
        }
    }
elif database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=600,
            ssl_require=False,
        )
    }
elif USE_POSTGRES and postgres_db and postgres_user and postgres_password:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": postgres_db,
            "USER": postgres_user,
            "PASSWORD": postgres_password,
            "HOST": postgres_host,
            "PORT": postgres_port,
            "CONN_MAX_AGE": 600,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")

USE_I18N = True
USE_TZ = True

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env_to_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_to_bool("SESSION_COOKIE_SECURE", SECURE_SSL_REDIRECT)
CSRF_COOKIE_SECURE = env_to_bool("CSRF_COOKIE_SECURE", SECURE_SSL_REDIRECT)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_to_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_to_bool("SECURE_HSTS_PRELOAD", False)

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Repere de version des fichiers statiques. Nginx les met en cache une semaine :
# incrementer cette valeur a chaque livraison force les navigateurs a recharger
# CSS et JS, sans quoi les agents continuent de voir l'ancienne interface.
ASSET_VERSION = os.getenv("ASSET_VERSION", "20260730-3")

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"
INTRANET_HOSTNAME = os.getenv("INTRANET_HOSTNAME", "intranet-dges.local")
INTRANET_URL = os.getenv("INTRANET_URL", f"http://{INTRANET_HOSTNAME}")
INTRANET_FALLBACK_URL = os.getenv("INTRANET_FALLBACK_URL", "")
MESSAGING_URL = os.getenv("MESSAGING_URL", "https://messagerie.dges.local")
MESSAGING_FALLBACK_URL = os.getenv("MESSAGING_FALLBACK_URL", "")

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DOCUMENT_MAX_UPLOAD_SIZE = int(os.getenv("DOCUMENT_MAX_UPLOAD_SIZE", str(20 * 1024 * 1024)))
DOCUMENT_ALLOWED_EXTENSIONS = tuple(
    extension.lower()
    for extension in env_to_list(
        "DOCUMENT_ALLOWED_EXTENSIONS",
        "pdf,doc,docx,xls,xlsx,csv,txt,png,jpg,jpeg,odt,ods",
    )
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------
# Journalisation
#
# Deux destinations : la sortie standard, que Docker capture et que
# `docker compose logs web` affiche, et un fichier tournant pour conserver
# une trace au-dela de la duree de vie du conteneur.
#
# Le repertoire peut ne pas etre creable (poste de developpement restreint,
# systeme de fichiers en lecture seule) : dans ce cas on se contente de la
# sortie standard plutot que d'empecher le demarrage.
# ---------------------------------------------------------------------

LOG_DIR = Path(os.getenv("DJANGO_LOG_DIR", str(BASE_DIR / "logs")))
# Pendant les tests, le journal n'apporte rien et masque les resultats.
LOG_LEVEL = "CRITICAL" if RUNNING_TESTS else os.getenv("DJANGO_LOG_LEVEL", "INFO").upper()

try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_FICHIER_DISPONIBLE = True
except OSError:
    JOURNAL_FICHIER_DISPONIBLE = False

_handlers = ["console"] + (["fichier"] if JOURNAL_FICHIER_DISPONIBLE else [])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detaille": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "detaille",
            "level": LOG_LEVEL,
        },
        **(
            {
                "fichier": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(LOG_DIR / "intranet.log"),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "encoding": "utf-8",
                    "formatter": "detaille",
                    "level": LOG_LEVEL,
                }
            }
            if JOURNAL_FICHIER_DISPONIBLE
            else {}
        ),
    },
    "root": {
        "handlers": _handlers,
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": _handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Les erreurs serveur doivent laisser une trace exploitable le
        # lendemain, pas seulement dans la console du conteneur.
        "django.request": {
            "handlers": _handlers,
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": _handlers,
            "level": "WARNING",
            "propagate": False,
        },
        # Journal applicatif : connexions, circuits, actions sensibles.
        "intranet": {
            "handlers": _handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
