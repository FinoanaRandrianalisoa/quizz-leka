from django.contrib import admin

from apps.themes.models import Theme, Question, Reponse


class ReponseInline(admin.TabularInline):
    model = Reponse
    extra = 4


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("nom", "slug", "actif")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "texte", "theme", "validee")
    list_filter = ("theme", "validee")
    inlines = [ReponseInline]
