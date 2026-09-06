from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("discussions", "0003_seed_villes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MessageAmi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("contenu", models.TextField()),
                (
                    "destinataire",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages_amis_recus",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "expediteur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages_amis_envoyes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["cree_le"],
            },
        ),
    ]
