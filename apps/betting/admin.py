from django.contrib import admin

from apps.betting.models import Pari, SignalFraude


@admin.register(Pari)
class PariAdmin(admin.ModelAdmin):
    list_display = ("id", "utilisateur", "match", "joueur_pari", "montant", "cote", "statut")
    list_filter = ("statut",)


@admin.register(SignalFraude)
class SignalFraudeAdmin(admin.ModelAdmin):
    list_display = ("type_anomalie", "match", "score_suspicion", "traite")
    list_filter = ("traite", "type_anomalie")