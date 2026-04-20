from .base import *
import dj_database_url

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Use dj_database_url to parse DATABASE_URL for pgvector
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://sales_user:sales_password@localhost:5432/sales_db",
        conn_max_age=600,
    )
}
