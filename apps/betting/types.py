import strawberry
import strawberry_django

from apps.betting import models
from apps.matches.types import MatchType
from apps.users.types import UtilisateurType


@strawberry_django.type(models.Pari)
class PariType:
    id: strawberry.auto
    montant: strawberry.auto
    cote: strawberry.auto
    statut: strawberry.auto
    match: MatchType
    joueur_pari: UtilisateurType
    cree_le: strawberry.auto

    @strawberry.field
    def gain_potentiel(self) -> str | None:
        gp = self.gain_potentiel
        return str(gp) if gp is not None else None


@strawberry_django.type(models.SignalFraude)
class SignalFraudeType:
    id: strawberry.auto
    type_anomalie: strawberry.auto
    score_suspicion: strawberry.auto
    details: strawberry.auto
    traite: strawberry.auto
    cree_le: strawberry.auto