import logging

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def _tables_ready() -> bool:
    try:
        names = connection.introspection.table_names()
        return "themes_theme" in names and "themes_question" in names
    except (OperationalError, ProgrammingError):
        return False


def ensure_seed_questions() -> None:
    """Importe les questions de base si aucun thème n'existe encore."""
    if not _tables_ready():
        return
    from apps.themes.models import Theme

    if Theme.objects.exists():
        return
    from django.core.management import call_command

    call_command("seed_questions", verbosity=0)
    logger.info("Questions de base importées au lancement.")
