from django.contrib import admin

from apps.moderation.models import Publicite, SignalementContenu


@admin.register(Publicite)
class PubliciteAdmin(admin.ModelAdmin):
    list_display = ("titre", "actif")
    list_filter = ("actif",)


@admin.register(SignalementContenu)
class SignalementContenuAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "motif", "statut", "content_type")
    list_filter = ("motif", "statut")