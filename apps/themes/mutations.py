import strawberry
from strawberry.types import Info

from apps.themes.models import Question, Reponse, Theme
from apps.themes.types import QuestionType, ReponseType
from common.graphql.errors import NotFoundError, ValidationError
from common.graphql.permissions import require_admin


@strawberry.input
class ReponseInput:
    texte: str
    est_correcte: bool = False


@strawberry.input
class QuestionInput:
    texte: str
    reponses: list[ReponseInput]


def _normalize_question_payload(texte: str, reponses: list[ReponseInput]) -> tuple[str, list[tuple[str, bool]]]:
    cleaned_texte = (texte or "").strip()
    if not cleaned_texte:
        raise ValidationError("Le texte de la question est requis.")
    normalized = []
    for item in reponses or []:
        cleaned = (item.texte or "").strip()
        if not cleaned:
            raise ValidationError("Chaque réponse doit contenir un texte.")
        normalized.append((cleaned, bool(item.est_correcte)))
    if len(normalized) < 4:
        raise ValidationError("Une question doit contenir au moins 4 réponses.")
    if sum(1 for _, is_correct in normalized if is_correct) != 1:
        raise ValidationError("Une question doit avoir exactement une bonne réponse.")
    return cleaned_texte, normalized


def resolve_create_question(info: Info, theme_id: int, texte: str, reponses: list[ReponseInput]) -> QuestionType:
    require_admin(info)
    try:
        theme = Theme.objects.get(pk=theme_id)
    except Theme.DoesNotExist:
        raise NotFoundError("Thème introuvable.")
    cleaned_texte, normalized = _normalize_question_payload(texte, reponses)
    question = Question.objects.create(theme=theme, texte=cleaned_texte, validee=True)
    Reponse.objects.bulk_create(
        [Reponse(question=question, texte=answer_text, est_correcte=is_correct) for answer_text, is_correct in normalized]
    )
    return question


def resolve_update_question(info: Info, question_id: int, texte: str, reponses: list[ReponseInput]) -> QuestionType:
    require_admin(info)
    try:
        question = Question.objects.select_related("theme").prefetch_related("reponses").get(pk=question_id)
    except Question.DoesNotExist:
        raise NotFoundError("Question introuvable.")
    cleaned_texte, normalized = _normalize_question_payload(texte, reponses)
    question.texte = cleaned_texte
    question.save(update_fields=["texte", "validee"])
    question.reponses.all().delete()
    Reponse.objects.bulk_create(
        [Reponse(question=question, texte=answer_text, est_correcte=is_correct) for answer_text, is_correct in normalized]
    )
    return question


def resolve_delete_question(info: Info, question_id: int) -> bool:
    require_admin(info)
    try:
        question = Question.objects.get(pk=question_id)
    except Question.DoesNotExist:
        raise NotFoundError("Question introuvable.")
    question.delete()
    return True


@strawberry.type
class ThemesMutation:
    create_question: QuestionType = strawberry.field(resolver=resolve_create_question)
    update_question: QuestionType = strawberry.field(resolver=resolve_update_question)
    delete_question: bool = strawberry.field(resolver=resolve_delete_question)
