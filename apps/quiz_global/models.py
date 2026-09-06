from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class QuizGlobalGame(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "WAITING"
        STARTING = "STARTING"
        THEME_SELECTION = "THEME_SELECTION"
        QUESTION_READING = "QUESTION_READING"
        ANSWERING = "ANSWERING"
        QUESTION_FINISHED = "QUESTION_FINISHED"
        TIE_BREAK = "TIE_BREAK"
        FINISHED = "FINISHED"
        CANCELLED = "CANCELLED"

    status = models.CharField(max_length=40, choices=Status.choices, default=Status.WAITING)
    target_questions = models.PositiveSmallIntegerField()
    current_turn = models.PositiveIntegerField(default=0)
    active_seat = models.CharField(max_length=1, default="A")
    invited_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_global_wins",
    )
    phase_started_at = models.DateTimeField(null=True, blank=True)
    phase_deadline = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-cree_le"]

    def __str__(self):
        return f"QuizGlobal #{self.pk} ({self.status})"


class QuizGlobalPlayer(TimeStampedModel):
    game = models.ForeignKey(QuizGlobalGame, on_delete=models.CASCADE, related_name="players")
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quiz_global_players")
    seat = models.CharField(max_length=1, choices=[("A", "Player A"), ("B", "Player B")])
    score = models.PositiveIntegerField(default=0)
    is_connected = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "player"], name="quiz_global_unique_player"),
            models.UniqueConstraint(fields=["game", "seat"], name="quiz_global_unique_seat"),
        ]


class QuizGlobalGameQuestion(TimeStampedModel):
    game = models.ForeignKey(QuizGlobalGame, on_delete=models.CASCADE, related_name="game_questions")
    question = models.ForeignKey("themes.Question", on_delete=models.PROTECT)
    theme = models.ForeignKey("themes.Theme", on_delete=models.PROTECT)
    turn_number = models.PositiveIntegerField()
    option_a = models.ForeignKey("themes.Reponse", on_delete=models.PROTECT, related_name="+")
    option_b = models.ForeignKey("themes.Reponse", on_delete=models.PROTECT, related_name="+")
    option_c = models.ForeignKey("themes.Reponse", on_delete=models.PROTECT, related_name="+")
    option_d = models.ForeignKey("themes.Reponse", on_delete=models.PROTECT, related_name="+")
    correct_option = models.CharField(max_length=1)
    is_tie_break = models.BooleanField(default=False)
    reading_started_at = models.DateTimeField(null=True, blank=True)
    answering_started_at = models.DateTimeField(null=True, blank=True)
    answer_deadline = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["game", "turn_number"]),
            models.Index(fields=["game", "question"]),
            models.Index(fields=["game", "theme"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["game", "turn_number"], name="quiz_global_unique_turn"),
            models.UniqueConstraint(fields=["game", "question"], name="quiz_global_unique_question"),
        ]


class QuizGlobalPlayerAnswer(TimeStampedModel):
    game_question = models.ForeignKey(
        QuizGlobalGameQuestion,
        on_delete=models.CASCADE,
        related_name="player_answers",
    )
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    selected_option = models.CharField(max_length=1)
    is_correct = models.BooleanField(null=True)
    points_awarded = models.PositiveSmallIntegerField(default=0)
    answered_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game_question", "player"],
                name="quiz_global_one_answer_per_player_per_question",
            )
        ]
        indexes = [
            models.Index(fields=["game_question", "player"]),
        ]
