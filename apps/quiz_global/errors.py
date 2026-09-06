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


__all__ = [
    "QuizGlobalError",
    "ThemeUnavailableError",
    "AnswerRejectedError",
    "GameNotJoinableError",
    "ValidationError",
    "MatchNotFoundError",
    "NotYourTurnError",
]
