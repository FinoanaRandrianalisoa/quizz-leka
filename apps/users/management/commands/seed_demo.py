from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.discussions.models import Ville
from apps.social.models import Publication
from apps.users.models import Utilisateur
from apps.wallet.models import LedgerEntry
from apps.wallet import services as wallet_services

VILLES = [
    ("Antananarivo", "antananarivo"),
    ("Toamasina", "toamasina"),
    ("Mahajanga", "mahajanga"),
    ("Fianarantsoa", "fianarantsoa"),
    ("Antsirabe", "antsirabe"),
    ("Toliara", "toliara"),
    ("Antsiranana", "antsiranana"),
    ("Morondava", "morondava"),
]

# DEMO_USERS = [
#     {
#         "email": "rakoto@example.mg",
#         "pseudo": "Rakoto",
#         "password": "MotDePasse1!",
#         "ville": "Antananarivo",
#         "code_parent": None,
#         "depot": "100.00",
#     },
#     {
#         "email": "rabe@example.mg",
#         "pseudo": "Rabe",
#         "password": "MotDePasse1!",
#         "ville": "Toamasina",
#         "code_parent": "rakoto@example.mg",
#         "depot": "50.00",
#     },
#     {
#         "email": "rasoa@example.mg",
#         "pseudo": "Rasoa",
#         "password": "MotDePasse1!",
#         "ville": "Antsirabe",
#         "code_parent": None,
#         "depot": "0",
#     },
# ]


@transaction.atomic
def seed():
    call_command("seed_questions", verbosity=0)

    for nom, slug in VILLES:
        Ville.objects.get_or_create(nom=nom, slug=slug)

    utilisateurs = {}
    for data in DEMO_USERS:
        email = data["email"]
        utilisateur, cree = Utilisateur.objects.get_or_create(
            email=email,
            defaults={
                "email": email,
                "username": email,
                "pseudo": data["pseudo"],
                "ville_origine": data["ville"],
            },
        )
        if cree:
            utilisateur.set_password(data["password"])
        else:
            utilisateur.username = email
            utilisateur.pseudo = data["pseudo"]
            utilisateur.ville_origine = data["ville"]
        parent_email = data["code_parent"]
        if parent_email:
            utilisateur.code_parent = utilisateurs[parent_email].code_parrain
        utilisateur.save()
        utilisateurs[email] = utilisateur

        depot = Decimal(data["depot"]) if data["depot"] else Decimal("0")
        reference_depot = f"seed-demo-{email}"
        if (
            depot > 0
            and not LedgerEntry.objects.filter(reference=reference_depot).exists()
        ):
            wallet_services.crediter(
                utilisateur.portefeuille,
                depot,
                LedgerEntry.Type.DEPOT,
                reference=reference_depot,
            )

    rakoto = utilisateurs["rakoto@example.mg"]
    if not Publication.objects.filter(auteur=rakoto).exists():
        Publication.objects.create(
            auteur=rakoto,
            texte=f"Salut Antananarivo ! Prêt pour un quiz ce soir ? Mon code parrain : {rakoto.code_parrain}",
        )


class Command(BaseCommand):
    help = "Données de démonstration (villes, comptes joueurs, saldo de départ)"

    def handle(self, *args, **options):
        seed()
        self.stdout.write(self.style.SUCCESS("seed_demo terminé :"))
        self.stdout.write("  Comptes : rakoto@example.mg / rabe@example.mg / rasoa@example.mg")
        self.stdout.write("  Mot de passe : MotDePasse1!")