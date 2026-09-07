import os
import logging

from django.core.wsgi import get_wsgi_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()
logger.info("WSGI application initialized. Django app ready — template render should be available.")
