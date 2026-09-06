from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _on_post_migrate(sender, **kwargs):
    from apps.themes.bootstrap import ensure_seed_questions

    ensure_seed_questions()


class ThemesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.themes"

    def ready(self):
        post_migrate.connect(_on_post_migrate, sender=self)
        try:
            from apps.themes.bootstrap import ensure_seed_questions

            ensure_seed_questions()
        except Exception:
            pass
