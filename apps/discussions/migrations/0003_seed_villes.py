from django.db import migrations


VILLES = [
    "Antsiranana",
    "Mahajanga",
    "Toamasina",
    "Antananarivo",
    "Antsirabe",
    "Fianarantsoa",
    "Toliara",
]


def seed_villes(apps, schema_editor):
    Ville = apps.get_model("discussions", "Ville")
    for nom in VILLES:
        Ville.objects.get_or_create(
            nom=nom,
            defaults={"slug": nom.lower().replace(" ", "-")},
        )


def reverse_seed_villes(apps, schema_editor):
    Ville = apps.get_model("discussions", "Ville")
    Ville.objects.filter(nom__in=VILLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("discussions", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(seed_villes, reverse_seed_villes),
    ]
