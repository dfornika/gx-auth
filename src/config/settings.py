"""Django settings for gx-auth.

Mirrors the gx-core conventions: environs for config, a `config/` project
package, mozilla-django-oidc for Cognito/Entra login, django-ninja for the API.
"""

from pathlib import Path

from environs import Env

env = Env()
env.read_env()

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

# --- Core -------------------------------------------------------------------

SECRET_KEY = env.str("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
]

INSTALLED_APPS += [
    "django_prodserver",
    "health_check",
    "ninja",  # registered for its export_openapi_schema management command
]

INSTALLED_APPS += [
    "accounts",
    "authz",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_USER_MODEL = "accounts.User"

# --- Database ---------------------------------------------------------------

# Prefer a single DATABASE_URL (local/compose); otherwise build from discrete
# vars so the password can be injected from a secret (deployed / Fargate).
if env.str("DATABASE_URL", default=""):
    DATABASES = {"default": env.dj_db_url("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env.str("DB_HOST", default="db"),
            "PORT": env.str("DB_PORT", default="5432"),
            "NAME": env.str("DB_NAME", default="gxauth"),
            "USER": env.str("DB_USER", default="postgres"),
            "PASSWORD": env.str("DB_PASSWORD", default=""),
            "OPTIONS": {"sslmode": env.str("DB_SSLMODE", default="prefer")},
        }
    }

# Name of the OpenFGA database created alongside gx-auth's (see ensure_openfga_db).
OPENFGA_DB_NAME = env.str("OPENFGA_DB_NAME", default="openfga")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --- i18n / static ----------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_ROOT = str(BASE_DIR / "static")
STATIC_URL = "/static/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

ADMIN_URL = env.str("ADMIN_URL", default="admin/")
LOGIN_URL = "/oidc/authenticate/"
LOGIN_REDIRECT_URL = "/api/docs"
LOGOUT_REDIRECT_URL = "/"

# --- OpenFGA ----------------------------------------------------------------

FGA_API_URL = env.str("FGA_API_URL", default="http://openfga:8080")
FGA_STORE_ID = env.str("FGA_STORE_ID", default="")
FGA_MODEL_ID = env.str("FGA_MODEL_ID", default="")  # empty -> use store's latest model

# --- Cognito / Entra OIDC (set OIDC_ENABLED=true to activate) ----------------
# See docs/004-identity-and-tokens.md. The token is identity-only; all
# authorization lives in OpenFGA. Swapping Cognito for Entra is a config change.

OIDC_ENABLED = env.bool("OIDC_ENABLED", default=False)
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

if OIDC_ENABLED:
    INSTALLED_APPS += ["mozilla_django_oidc"]
    AUTHENTICATION_BACKENDS += ["accounts.oidc.CognitoOIDCBackend"]

    OIDC_RP_CLIENT_ID = env.str("OIDC_RP_CLIENT_ID")
    OIDC_RP_CLIENT_SECRET = env.str("OIDC_RP_CLIENT_SECRET")
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_RP_SCOPES = "openid email profile"
    OIDC_STORE_ID_TOKEN = True

    # Endpoints. For Cognito set OIDC_COGNITO_DOMAIN + OIDC_COGNITO_POOL_URL;
    # for Entra, override the four *_ENDPOINT values below with the tenant's
    # OIDC discovery endpoints instead. Only the endpoints change on a pivot.
    _COGNITO_DOMAIN = env.str("OIDC_COGNITO_DOMAIN", default="")
    _COGNITO_POOL_URL = env.str("OIDC_COGNITO_POOL_URL", default="")
    if _COGNITO_DOMAIN:
        OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_COGNITO_DOMAIN}/oauth2/authorize"
        OIDC_OP_TOKEN_ENDPOINT = f"{_COGNITO_DOMAIN}/oauth2/token"
        OIDC_OP_USER_ENDPOINT = f"{_COGNITO_DOMAIN}/oauth2/userInfo"
        OIDC_OP_JWKS_ENDPOINT = f"{_COGNITO_POOL_URL}/.well-known/jwks.json"
        OIDC_OP_LOGOUT_ENDPOINT = f"{_COGNITO_DOMAIN}/logout"
    else:
        OIDC_OP_AUTHORIZATION_ENDPOINT = env.str("OIDC_OP_AUTHORIZATION_ENDPOINT")
        OIDC_OP_TOKEN_ENDPOINT = env.str("OIDC_OP_TOKEN_ENDPOINT")
        OIDC_OP_USER_ENDPOINT = env.str("OIDC_OP_USER_ENDPOINT")
        OIDC_OP_JWKS_ENDPOINT = env.str("OIDC_OP_JWKS_ENDPOINT")

    OIDC_REQUIRED_GROUP = env.str("OIDC_REQUIRED_GROUP", default="")
