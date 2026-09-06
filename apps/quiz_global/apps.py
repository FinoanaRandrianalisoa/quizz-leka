from django.apps import AppConfig


class QuizGlobalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.quiz_global"
    label = "quiz_global"
    verbose_name = "Quizz global"
