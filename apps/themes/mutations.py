import base64
import io

import openpyxl
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


def resolve_importer_questions_excel(info: Info, theme_id: int, fichier_base64: str) -> str:
    """
    Importe des questions depuis un fichier Excel encodé en base64.
    Format attendu:
    - Colonne A (index 0): Question
    - Colonne B (index 1): Vraie réponse (est_correcte = True)
    - Colonne C et suivantes (index 2+): Fausses réponses (est_correcte = False)
    """
    require_admin(info)
    try:
        theme = Theme.objects.get(pk=theme_id)
    except Theme.DoesNotExist:
        raise NotFoundError("Thème introuvable.")
    
    try:
        # Décoder le fichier base64
        file_data = base64.b64decode(fichier_base64)
        workbook = openpyxl.load_workbook(io.BytesIO(file_data))
        sheet = workbook.active
        
        questions_importees = 0
        questions_erreur = 0
        
        for row in sheet.iter_rows(min_row=1, values_only=True):
            if not row or len(row) < 2:
                continue
            
            # Extraire les données
            question_text = str(row[0]).strip() if row[0] else ""
            vraie_reponse = str(row[1]).strip() if row[1] else ""
            fausses_reponses = [str(cell).strip() for cell in row[2:] if cell and str(cell).strip()]
            
            # Valider les données
            if not question_text or not vraie_reponse:
                questions_erreur += 1
                continue
            
            # Combiner toutes les réponses
            toutes_reponses = [(vraie_reponse, True)] + [(r, False) for r in fausses_reponses]
            
            # Valider qu'on a au moins 4 réponses
            if len(toutes_reponses) < 4:
                questions_erreur += 1
                continue
            
            # Créer la question
            question = Question.objects.create(theme=theme, texte=question_text, validee=True)
            
            # Créer les réponses en bulk
            Reponse.objects.bulk_create([
                Reponse(question=question, texte=answer_text, est_correcte=is_correct)
                for answer_text, is_correct in toutes_reponses
            ])
            
            questions_importees += 1
        
        workbook.close()
        
        return f"Import terminé: {questions_importees} questions importées, {questions_erreur} erreurs."
    
    except Exception as e:
        raise ValidationError(f"Erreur lors de l'import: {str(e)}")


@strawberry.type
class ThemesMutation:
    create_question: QuestionType = strawberry.field(resolver=resolve_create_question)
    update_question: QuestionType = strawberry.field(resolver=resolve_update_question)
    delete_question: bool = strawberry.field(resolver=resolve_delete_question)
    importer_questions_excel: str = strawberry.field(resolver=resolve_importer_questions_excel)
