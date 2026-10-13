import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

INSTALLED_APPS = ["corsheaders", "routing"]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves the built React app (frontend/dist) from the same service.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Stateless API: no models, so no database is needed.
DATABASES = {}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")

WHITENOISE_ROOT = BASE_DIR.parent / "frontend" / "dist"
WHITENOISE_INDEX_FILE = True
STATIC_URL = "/static/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
