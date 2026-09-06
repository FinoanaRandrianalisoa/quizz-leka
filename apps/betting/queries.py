import strawberry
from strawberry.types import Info

from apps.betting.models import Pari
from apps.betting.types import PariType
from common.graphql.permissions import get_current_user


def resolve_mes_paris(info: Info, limit: int = 20) -> list[PariType]:
    return list(
        Pari.objects.filter(utilisateur=get_current_user(info))
        .select_related("match", "joueur_pari")
        .order_by("-cree_le")[: min(limit, 50)]
    )


def resolve_paris_match(info: Info, match_id: int, limit: int = 50) -> list[PariType]:
    return list(
        Pari.objects.filter(match_id=match_id)
        .select_related("match", "joueur_pari")
        .order_by("-cree_le")[: min(limit, 100)]
    )


@strawberry.type
class BettingQuery:
    mes_paris: list[PariType] = strawberry.field(resolver=resolve_mes_paris)
    paris_match: list[PariType] = strawberry.field(resolver=resolve_paris_match)