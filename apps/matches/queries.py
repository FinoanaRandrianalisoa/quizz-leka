from django.db.models import Q
import strawberry
from strawberry.types import Info

from apps.matches import services
from apps.matches.models import Match, Tour, ReponseTour, Participation
from apps.matches.types import MatchType, RpsChallengeType, RpsMatchType, PenaltyChallengeType, PenaltyMatchType
from common.graphql.permissions import get_current_user


def resolve_parties_disponibles(info: Info, limit: int = 20) -> list[MatchType]:
    return list(
        Match.objects.filter(statut=Match.Statut.EN_ATTENTE, joueur_invite__isnull=True)
        .select_related("theme", "joueur_hote")
        .order_by("-cree_le")[: min(limit, 50)]
    )


def resolve_parties_en_cours(info: Info, limit: int = 20) -> list[MatchType]:
    return list(
        Match.objects.filter(statut=Match.Statut.EN_COURS)
        .select_related("theme", "joueur_hote", "joueur_invite")
        .order_by("-commence_le", "-cree_le")[: min(limit, 50)]
    )


def resolve_mes_parties(info: Info, limit: int = 20) -> list[MatchType]:
    user = get_current_user(info)
    return list(
        Match.objects.filter(Q(joueur_hote=user) | Q(joueur_invite=user))
        .select_related("theme", "joueur_hote", "joueur_invite", "vainqueur")
        .order_by("-cree_le")[: min(limit, 50)]
    )


def resolve_match_par_id(info: Info, match_id: int) -> MatchType | None:
    return (
        Match.objects.select_related("theme", "joueur_hote", "joueur_invite", "vainqueur")
        .filter(pk=match_id)
        .first()
    )


def resolve_mes_defis_rps(info: Info) -> list[RpsChallengeType]:
    user = get_current_user(info)
    challenges = []
    for challenge in services.RPS_CHALLENGES.values():
        if challenge.get("to_id") == user.pk:
            challenges.append(
                RpsChallengeType(
                    id=challenge["id"],
                    from_id=challenge["from_id"],
                    from_pseudo=challenge["from_pseudo"],
                    to_id=challenge["to_id"],
                    to_pseudo=challenge.get("to_pseudo"),
                    created=challenge["created"],
                )
            )
    return challenges


def resolve_mes_matchs_rps(info: Info) -> list[RpsMatchType]:
    user = get_current_user(info)
    matches = []
    for match in services.RPS_MATCHES.values():
        if str(user.pk) in {str(match["joueur_hote_id"]), str(match["joueur_invite_id"])}:
            matches.append(
                RpsMatchType(
                    id=match["id"],
                    joueur_hote_id=match["joueur_hote_id"],
                    joueur_hote_pseudo=match["joueur_hote_pseudo"],
                    joueur_invite_id=match["joueur_invite_id"],
                    joueur_invite_pseudo=match["joueur_invite_pseudo"],
                    score_hote=match["score_hote"],
                    score_invite=match["score_invite"],
                    score_cible=match["score_cible"],
                    round=match["round"],
                    statut=match["statut"],
                )
            )
    return matches


def resolve_mes_defis_penalty(info: Info) -> list[PenaltyChallengeType]:
    user = get_current_user(info)
    challenges = []
    for challenge in services.mes_defis_penalty(user):
        challenges.append(
            PenaltyChallengeType(
                id=challenge["id"],
                hote_id=challenge["hote_id"],
                hote_pseudo=challenge["hote_pseudo"],
                invite_id=challenge["invite_id"],
                invite_pseudo=challenge.get("invite_pseudo"),
                score_cible=challenge["score_cible"],
                statut=challenge["statut"],
            )
        )
    return challenges


def resolve_parties_rps_disponibles(info: Info) -> list[RpsMatchType]:
    matches = []
    for match in services.RPS_MATCHES.values():
        if match.get("statut") == "en_cours":
            matches.append(
                RpsMatchType(
                    id=match["id"],
                    joueur_hote_id=match["joueur_hote_id"],
                    joueur_hote_pseudo=match["joueur_hote_pseudo"],
                    joueur_invite_id=match["joueur_invite_id"],
                    joueur_invite_pseudo=match["joueur_invite_pseudo"],
                    score_hote=match["score_hote"],
                    score_invite=match["score_invite"],
                    score_cible=match["score_cible"],
                    round=match["round"],
                    statut=match["statut"],
                )
            )
    return matches


def resolve_mes_matchs_penalty(info: Info) -> list[PenaltyMatchType]:
    utilisateur = get_current_user(info)
    if not utilisateur:
        return []
    matches = []
    for match in services.mes_matchs_penalty(utilisateur):
        matches.append(
            PenaltyMatchType(
                id=match["id"],
                joueur_hote_id=match["joueur_hote_id"],
                joueur_hote_pseudo=match["joueur_hote_pseudo"],
                joueur_invite_id=match["joueur_invite_id"],
                joueur_invite_pseudo=match["joueur_invite_pseudo"],
                score_hote=match["score_hote"],
                score_invite=match["score_invite"],
                score_cible=match["score_cible"],
                round=match["round"],
                statut=match["statut"],
                resultat_manche=match.get("resultat_manche"),
                vainqueur_id=match.get("winner_id"),
            )
        )
    return matches


def resolve_parties_penalty_disponibles(info: Info) -> list[PenaltyMatchType]:
    matches = []
    for match in services.parties_penalty_disponibles():
        matches.append(
            PenaltyMatchType(
                id=match["id"],
                joueur_hote_id=match["joueur_hote_id"],
                joueur_hote_pseudo=match["joueur_hote_pseudo"],
                joueur_invite_id=match["joueur_invite_id"],
                joueur_invite_pseudo=match["joueur_invite_pseudo"],
                score_hote=match["score_hote"],
                score_invite=match["score_invite"],
                score_cible=match["score_cible"],
                round=match["round"],
                statut=match["statut"],
                resultat_manche=match.get("resultat_manche"),
                vainqueur_id=match.get("winner_id"),
            )
        )
    return matches


@strawberry.type
class MatchesQuery:
    parties_disponibles: list[MatchType] = strawberry.field(resolver=resolve_parties_disponibles)
    parties_en_cours: list[MatchType] = strawberry.field(resolver=resolve_parties_en_cours)
    mes_parties: list[MatchType] = strawberry.field(resolver=resolve_mes_parties)
    match_par_id: MatchType | None = strawberry.field(resolver=resolve_match_par_id)
    mes_defis_rps: list[RpsChallengeType] = strawberry.field(resolver=resolve_mes_defis_rps)
    mes_defis_penalty: list[PenaltyChallengeType] = strawberry.field(resolver=resolve_mes_defis_penalty)
    mes_matchs_rps: list[RpsMatchType] = strawberry.field(resolver=resolve_mes_matchs_rps)
    parties_rps_disponibles: list[RpsMatchType] = strawberry.field(resolver=resolve_parties_rps_disponibles)
    mes_matchs_penalty: list[PenaltyMatchType] = strawberry.field(resolver=resolve_mes_matchs_penalty)
    parties_penalty_disponibles: list[PenaltyMatchType] = strawberry.field(resolver=resolve_parties_penalty_disponibles)