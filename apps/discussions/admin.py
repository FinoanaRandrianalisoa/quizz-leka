from django.contrib import admin

from apps.discussions.models import Ville, Message


@admin.register(Ville)
class VilleAdmin(admin.ModelAdmin):
    list_display = ("nom", "slug")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("ville", "utilisateur", "contenu")
    search_fields = ("contenu",)