import strawberry
import strawberry_django

from apps.matches import models
from apps.themes.types import QuestionType, ThemeType
from apps.users.types import UtilisateurType


@strawberry_django.type(models.Tour)
class TourType:
    id: strawberry.auto
    numero: strawberry.auto
    statut: strawberry.auto
    question: QuestionType


@strawberry_django.type(models.Match)
class MatchType:
    id: strawberry.auto
    type_jeu: strawberry.auto
    statut: strawberry.auto
    theme: ThemeType
    mise: strawberry.auto
    mise_proposee_invite: strawberry.auto
    score_cible: strawberry.auto
    joueur_hote: UtilisateurType
    joueur_invite: UtilisateurType | None
    vainqueur: UtilisateurType | None
    score_hote: strawberry.auto
    score_invite: strawberry.auto
    tour_actuel: strawberry.auto
    cree_le: strawberry.auto
    commence_le: strawberry.auto
    termine_le: strawberry.auto

    @strawberry.field
    def complet(self) -> bool:
        return self.joueur_invite_id is not None

    @strawberry.field
    def mise_effective(self) -> str:
        return f"{self.mise_effective:.2f}"

    @strawberry.field
    def invite_accepte(self) -> bool:
        return bool(self.joueur_invite_id and self.commence_le)

    @strawberry.field
    def premier_tiers_atteint(self) -> bool:
        return self.premier_tiers_atteint

    @strawberry.field
    def tour_en_cours(self) -> TourType | None:
        return (
            self.tours.filter(statut=models.Tour.Statut.EN_COURS)
            .select_related("question", "question__theme")
            .prefetch_related("question__reponses")
            .order_by("-numero")
            .first()
        )


@strawberry.type
class RpsChallengeType:
    id: strawberry.ID
    from_id: strawberry.ID
    from_pseudo: str
    to_id: strawberry.ID
    to_pseudo: str | None = None
    score_cible: int = 3
    created: str


@strawberry.type
class RpsMatchType:
    id: strawberry.ID
    joueur_hote_id: strawberry.ID
    joueur_hote_pseudo: str
    joueur_invite_id: strawberry.ID
    joueur_invite_pseudo: str
    score_hote: int = 0
    score_invite: int = 0
    score_cible: int = 3
    round: int = 1
    statut: str = "en_cours"
    resultat_manche: str | None = None
    vainqueur_id: strawberry.ID | None = None


@strawberry.type
class PenaltyChallengeType:
    id: strawberry.ID
    hote_id: strawberry.ID
    hote_pseudo: str
    invite_id: strawberry.ID
    invite_pseudo: str | None = None
    score_cible: int = 5
    statut: str = "en_attente"


@strawberry.type
class PenaltyMatchType:
    id: strawberry.ID
    joueur_hote_id: strawberry.ID
    joueur_hote_pseudo: str
    joueur_invite_id: strawberry.ID
    joueur_invite_pseudo: str
    score_hote: int = 0
    score_invite: int = 0
    score_cible: int = 5
    round: int = 1
    statut: str = "en_cours"
    resultat_manche: str | None = None
    vainqueur_id: strawberry.ID | None = None