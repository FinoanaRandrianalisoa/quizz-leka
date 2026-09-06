from django.contrib import admin

from apps.matches.models import Match, Tour, ReponseTour, Participation


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("id", "theme", "statut", "type_jeu", "joueur_hote", "joueur_invite", "score_hote", "score_invite", "mise")
    list_filter = ("statut", "type_jeu", "theme")
    search_fields = ("joueur_hote__email", "joueur_invite__email")


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ("match", "numero", "question", "statut")
    list_filter = ("statut",)


@admin.register(ReponseTour)
class ReponseTourAdmin(admin.ModelAdmin):
    list_display = ("tour", "utilisateur", "reponse", "correcte", "duree_ms")
    list_filter = ("correcte",)


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ("match", "utilisateur", "score_final", "vainqueur")
    list_filter = ("vainqueur",)