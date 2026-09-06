from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.betting import services
from apps.betting.types import PariType
from apps.matches.models import Match
from common.graphql.errors import MatchNotFoundError
from common.graphql.permissions import get_current_user


@strawberry.type
class BettingMutation:
    @strawberry.mutation
    def placer_pari(
        info: Info,
        match_id: int,
        joueur_id: int,
        montant: Decimal,
        idempotency_key: str = "",
    ) -> PariType:
        match = Match.objects.select_related("joueur_hote", "joueur_invite").filter(pk=match_id).first()
        if not match:
            raise MatchNotFoundError()
        return services.placer_pari(
            get_current_user(info),
            match,
            joueur_id=joueur_id,
            montant=montant,
            idempotency_key=idempotency_key,
        )