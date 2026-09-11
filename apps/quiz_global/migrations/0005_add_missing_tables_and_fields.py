# Generated manually to fix missing tables and columns on Railway

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz_global', '0004_quizglobalgame_abandoned_at_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Ensure expired_at field exists
        migrations.AddField(
            model_name='quizglobalgame',
            name='expired_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Ensure abandoned_at field exists
        migrations.AddField(
            model_name='quizglobalgame',
            name='abandoned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Ensure QuizGlobalActivePlayer table exists
        migrations.CreateModel(
            name='QuizGlobalActivePlayer',
            fields=[
                ('player', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='quiz_global_active', serialize=False, to=settings.AUTH_USER_MODEL)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='active_players', to='quiz_global.quizglobalgame')),
            ],
        ),
        # Ensure QuizGlobalInvitation table exists
        migrations.CreateModel(
            name='QuizGlobalInvitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING', 'En attente'), ('ACCEPTED', 'Acceptée'), ('EXPIRED', 'Expirée'), ('CANCELLED', 'Annulée')], default='PENDING', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='quiz_global.quizglobalgame')),
                ('receiver', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quiz_global_invitations_received', to=settings.AUTH_USER_MODEL)),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quiz_global_invitations_sent', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['receiver', 'status'], name='quiz_global_receive_72b972_idx'), models.Index(fields=['game', 'status'], name='quiz_global_game_id_a562c8_idx')],
                'constraints': [models.UniqueConstraint(fields=('game', 'receiver'), name='quiz_global_unique_invitee')],
            },
        ),
    ]
