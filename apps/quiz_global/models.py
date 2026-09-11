from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class QuizGlobalGame(TimeStampedModel):
    class Status(models.TextChoices):
        WAITING = "WAITING"
        THEME_SELECTION = "THEME_SELECTION"
        QUESTION_READING = "QUESTION_READING"
        ANSWERING = "ANSWERING"
        QUESTION_FINISHED = "QUESTION_FINISHED"
        TIE_BREAK_THEME = "TIE_BREAK_THEME"
        FINISHED = "FINISHED"
        CANCELLED = "CANCELLED"
        EXPIRED = "EXPIRED"
        ABANDONED = "ABANDONED"

    status = models.CharField(max_length=40, choices=Status.choices, default=Status.WAITING)
    target_questions = models.PositiveSmallIntegerField()
    mise = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    mise_proposee_invite = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
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
    expired_at = models.DateTimeField(null=True, blank=True)
    abandoned_at = models.DateTimeField(null=True, blank=True)

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


class QuizGlobalActivePlayer(models.Model):
    """Verrou de « une seule partie active par joueur ».

    Une ligne par joueur au maximum (OneToOne) : la base refuse donc
    physiquement la création d'une seconde partie active pour le même joueur,
    même en cas de course concurrente non couverte par un verrou applicatif.
    """

    player = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="quiz_global_active",
    )
    game = models.ForeignKey(
        QuizGlobalGame,
        on_delete=models.CASCADE,
        related_name="active_players",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ActivePlayer(user={self.player_id}, game={self.game_id})"


class QuizGlobalInvitation(models.Model):
    """Invitation ciblée d'un hôte vers un joueur.

    Un hôte peut envoyer plusieurs invitations (vers B, C, D…) pour un même
    salon ; le premier joueur qui accepte obtient la place B, les autres
    invitations passent à EXPIRED.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        ACCEPTED = "ACCEPTED", "Acceptée"
        EXPIRED = "EXPIRED", "Expirée"
        CANCELLED = "CANCELLED", "Annulée"

    game = models.ForeignKey(QuizGlobalGame, on_delete=models.CASCADE, related_name="invitations")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_global_invitations_sent")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_global_invitations_received")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "receiver"], name="quiz_global_unique_invitee"),
        ]
        indexes = [
            models.Index(fields=["receiver", "status"]),
            models.Index(fields=["game", "status"]),
        ]

    def __str__(self):
        return f"Invitation(user={self.sender_id} -> {self.receiver_id}, game={self.game_id}, {self.status})"


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
