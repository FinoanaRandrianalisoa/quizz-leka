from django.core.management.base import BaseCommand

from apps.users.bootstrap import ensure_bootstrap_admin


class Command(BaseCommand):
    help = "Crée le compte administrateur de lancement s'il n'existe pas encore."

    def handle(self, *args, **options):
        ensure_bootstrap_admin()
        self.stdout.write(self.style.SUCCESS("ensure_admin : compte admin vérifié."))
