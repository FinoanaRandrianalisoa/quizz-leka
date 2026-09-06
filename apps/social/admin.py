from django.contrib import admin

from apps.social.models import Notification, Publication, Commentaire, Reaction, DemandeAmi


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ("id", "auteur", "texte", "statut")
    list_filter = ("statut",)


@admin.register(Commentaire)
class CommentaireAdmin(admin.ModelAdmin):
    list_display = ("publication", "auteur", "texte")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("publication", "auteur", "type")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "type", "titre", "lu", "cree_le")
    list_filter = ("type", "lu")
    search_fields = ("titre", "message")


@admin.register(DemandeAmi)
class DemandeAmiAdmin(admin.ModelAdmin):
    list_display = ("demandeur", "receveur", "statut")
    list_filter = ("statut",)