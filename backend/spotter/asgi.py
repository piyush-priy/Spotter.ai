"""ASGI config for spotter project (supports async views)."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spotter.settings.dev")
application = get_asgi_application()

