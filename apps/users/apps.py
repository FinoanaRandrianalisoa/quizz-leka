from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _on_post_migrate(sender, **kwargs):
    from apps.users.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin()


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        import apps.users.signals  # noqa: F401

        post_migrate.connect(_on_post_migrate, sender=self)
        try:
            from apps.users.bootstrap import ensure_bootstrap_admin

            ensure_bootstrap_admin()
        except Exception:
            # Tables absentes (premier migrate) ou connexion indisponible.
            pass
