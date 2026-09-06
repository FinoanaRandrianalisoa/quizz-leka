from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social", "0003_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="publication",
            name="lien_type",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="publication",
            name="reference_id",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]