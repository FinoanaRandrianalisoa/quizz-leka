import strawberry
from strawberry.types import Info

from apps.themes.models import Question, Reponse, Theme
from apps.themes.types import QuestionType, ThemeType
from common.graphql.errors import NotFoundError


def resolve_themes(info: Info) -> list[ThemeType]:
    return list(Theme.objects.filter(actif=True).order_by("nom"))


def resolve_questions(info: Info, theme_id: int, limit: int = 20, offset: int = 0) -> list[QuestionType]:
    qs = Question.objects.filter(validee=True, theme_id=theme_id).select_related("theme").prefetch_related("reponses")
    return list(qs[offset : offset + min(limit, 50)])


def resolve_reponse_correcte(info: Info, reponse_id: int) -> bool:
    reponse = Reponse.objects.filter(pk=reponse_id).first()
    if reponse is None:
        raise NotFoundError("Réponse introuvable.")
    return reponse.est_correcte


@strawberry.type
class ThemesQuery:
    themes: list[ThemeType] = strawberry.field(resolver=resolve_themes)
    questions: list[QuestionType] = strawberry.field(resolver=resolve_questions)
    reponse_correcte: bool = strawberry.field(resolver=resolve_reponse_correcte)
