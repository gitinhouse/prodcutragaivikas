from .base import *
import os

DEBUG = False

# [SECURITY] Set this to your actual production domain
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

# [SECURITY] Force HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Database logic remains in base.py using DATABASE_URL
# Static/Media paths for production (e.g., S3 or Nginx served)
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
