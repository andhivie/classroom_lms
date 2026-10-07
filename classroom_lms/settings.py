"""
Django settings for classroom_lms project.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ----------------------------------------------------------------
# Base directory
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------
# Load environment variables from .env
# ----------------------------------------------------------------
load_dotenv(BASE_DIR / '.env')

# ----------------------------------------------------------------
# Security
# ----------------------------------------------------------------
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY is not set. Please create a .env file with SECRET_KEY=<your-key>."
    )

DEBUG = os.getenv('DEBUG', 'False').strip().lower() == 'true'

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

# ----------------------------------------------------------------
# Applications
# ----------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'lms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'classroom_lms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'classroom_lms.wsgi.application'

# ----------------------------------------------------------------
# Database
# ----------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ----------------------------------------------------------------
# Password validation
# ----------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ----------------------------------------------------------------
# Internationalization
# ----------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ----------------------------------------------------------------
# Static files
# ----------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ----------------------------------------------------------------
# Media files
# ----------------------------------------------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ----------------------------------------------------------------
# Authentication redirects
# ----------------------------------------------------------------
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# ----------------------------------------------------------------
# Default primary key field type
# ----------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'