import strawberry
import strawberry_django

from apps.themes import models


@strawberry_django.type(models.Reponse)
class ReponseType:
    id: strawberry.auto
    texte: strawberry.auto
    est_correcte: strawberry.auto


@strawberry_django.type(models.Theme)
class ThemeType:
    id: strawberry.auto
    nom: strawberry.auto
    slug: strawberry.auto
    description: strawberry.auto
    icone: strawberry.auto
    category: strawberry.auto

    @strawberry.field
    def nombre_questions(self) -> int:
        return self.questions.filter(validee=True).count()


@strawberry_django.type(models.Question)
class QuestionType:
    id: strawberry.auto
    theme: ThemeType
    texte: strawberry.auto
    validee: strawberry.auto

    @strawberry.field
    def choix(self) -> list[ReponseType]:
        return list(self.reponses.all())
