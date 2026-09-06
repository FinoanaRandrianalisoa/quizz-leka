# Generated manually: add category field to Theme with default 'Quizz'
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("themes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="theme",
            name="category",
            field=models.CharField(max_length=50, default="Quizz"),
            preserve_default=False,
        ),
    ]
