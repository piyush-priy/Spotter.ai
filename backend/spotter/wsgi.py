"""WSGI config for spotter project."""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter.settings.dev")
application = get_wsgi_application()

