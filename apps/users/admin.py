from django.contrib import admin

from apps.users.models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ("email", "pseudo", "role", "ville_origine", "en_ligne")
    search_fields = ("email", "pseudo", "code_parrain")
