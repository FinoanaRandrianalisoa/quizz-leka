from django.contrib import admin

from apps.quiz_global.models import QuizGlobalGame, QuizGlobalGameQuestion, QuizGlobalPlayer, QuizGlobalPlayerAnswer


@admin.register(QuizGlobalGame)
class QuizGlobalGameAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "target_questions", "current_turn", "active_seat", "winner")


@admin.register(QuizGlobalPlayer)
class QuizGlobalPlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "player", "seat", "score")


@admin.register(QuizGlobalGameQuestion)
class QuizGlobalGameQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "turn_number", "theme", "correct_option", "is_tie_break", "finished_at")


@admin.register(QuizGlobalPlayerAnswer)
class QuizGlobalPlayerAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "game_question", "player", "selected_option", "is_correct", "points_awarded")
