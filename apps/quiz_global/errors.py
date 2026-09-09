from common.graphql.errors import DomainError, ValidationError, MatchNotFoundError, NotYourTurnError


class QuizGlobalError(DomainError):
    code = "QUIZ_GLOBAL_ERROR"
    default_message = "Impossible de traiter cette action de Quizz global."


class ThemeUnavailableError(QuizGlobalError):
    code = "THEME_UNAVAILABLE"
    default_message = "Ce thème n'a plus de questions disponibles. Veuillez choisir un autre thème."


class AnswerRejectedError(QuizGlobalError):
    code = "ANSWER_REJECTED"
    default_message = "Cette réponse ne peut pas être enregistrée."


class GameNotJoinableError(QuizGlobalError):
    code = "MATCH_NOT_JOINABLE"
    default_message = "Cette partie ne peut pas être rejointe."


class GameFullError(GameNotJoinableError):
    code = "GAME_FULL"
    default_message = "Un autre joueur a déjà rejoint cette partie."


class GameCancelledError(QuizGlobalError):
    code = "GAME_CANCELLED"
    default_message = "Cette partie a été annulée."


class InvalidTransitionError(QuizGlobalError):
    code = "INVALID_TRANSITION"
    default_message = "Transition de statut invalide."


class PlayerAlreadyInGameError(QuizGlobalError):
    code = "PLAYER_ALREADY_IN_GAME"
    default_message = "Vous êtes déjà engagé dans une autre partie."


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "WAITING": {"THEME_SELECTION", "CANCELLED", "EXPIRED"},
    "THEME_SELECTION": {"QUESTION_READING", "ABANDONED"},
    "QUESTION_READING": {"ANSWERING", "ABANDONED"},
    "ANSWERING": {"QUESTION_FINISHED", "ABANDONED"},
    "QUESTION_FINISHED": {
        "QUESTION_READING",
        "THEME_SELECTION",
        "TIE_BREAK_THEME",
        "FINISHED",
        "ABANDONED",
    },
    "TIE_BREAK_THEME": {"QUESTION_READING", "FINISHED", "ABANDONED"},
    "FINISHED": set(),
    "CANCELLED": set(),
    "EXPIRED": set(),
    "ABANDONED": set(),
}


def validate_transition(current_status: str, new_status: str) -> None:
    """Vérifie que la transition d'état est autorisée par la machine d'états."""
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidTransitionError(
            f"Transition interdite : {current_status} -> {new_status}"
        )


__all__ = [
    "QuizGlobalError",
    "ThemeUnavailableError",
    "AnswerRejectedError",
    "GameNotJoinableError",
    "GameFullError",
    "GameCancelledError",
    "InvalidTransitionError",
    "PlayerAlreadyInGameError",
    "ALLOWED_TRANSITIONS",
    "validate_transition",
    "ValidationError",
    "MatchNotFoundError",
    "NotYourTurnError",
]
