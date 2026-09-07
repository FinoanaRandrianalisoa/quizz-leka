#!/usr/bin/env python
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    # Try importing the settings module early so we can log helpful errors
    try:
        import importlib

        importlib.import_module(os.environ["DJANGO_SETTINGS_MODULE"])
        logger.info("Django settings module '%s' imported successfully.", os.environ["DJANGO_SETTINGS_MODULE"])
    except Exception as e:
        logger.exception("Failed to import Django settings (%s): %s", os.environ.get("DJANGO_SETTINGS_MODULE"), e)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
