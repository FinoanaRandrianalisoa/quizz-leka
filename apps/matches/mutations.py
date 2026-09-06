from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.matches import services
from apps.matches.types import MatchType, RpsChallengeType, RpsMatchType, PenaltyMatchType, PenaltyChallengeType
from common.graphql.permissions import get_current_user
from common.graphql.errors import PermissionDeniedError


# ==================== PENALTY KICK INPUT TYPE ====================

@strawberry.input
class PenaltyMatchInput:
    invite_id: str
    score_cible: int = 5


# ==================== MATCHES MUTATIONS ====================


@strawberry.type
class MatchesMutation:
    @strawberry.mutation
    def creer_partie(
        info: Info,
        theme_id: int,
        mise: Decimal = Decimal("0"),
        score_cible: int = 8,
        type_jeu: str = "classique",
    ) -> MatchType:
        return services.creer_partie(
            get_current_user(info),
            theme_id=theme_id,
            mise=mise,
            score_cible=score_cible,
            type_jeu=type_jeu,
        )

    @strawberry.mutation
    def rejoindre_partie(info: Info, match_id: int, mise: Decimal | None = None) -> MatchType:
        return services.rejoindre_partie(get_current_user(info), match_id, mise=mise)

    @strawberry.mutation
    def soumettre_reponse(info: Info, tour_id: int, reponse_id: int, duree_ms: int = 0) -> bool:
        return services.soumettre_reponse(
            get_current_user(info),
            tour_id=tour_id,
            reponse_id=reponse_id,
            duree_ms=duree_ms,
        )

    @strawberry.mutation
    def annuler_partie(info: Info, match_id: int) -> bool:
        return services.annuler_partie(get_current_user(info), match_id)

    @strawberry.mutation
    def inviter_joueur_course_lapin(info: Info, match_id: int, invite_id: int) -> MatchType:
        return services.inviter_joueur_course_lapin(get_current_user(info), match_id, invite_id)

    @strawberry.mutation
    def accepter_invitation_course_lapin(info: Info, match_id: int) -> MatchType:
        return services.accepter_invitation_course_lapin(get_current_user(info), match_id)

    @strawberry.mutation
    def refuser_invitation_course_lapin(info: Info, match_id: int) -> MatchType:
        return services.refuser_invitation_course_lapin(get_current_user(info), match_id)

    @strawberry.mutation
    def lancer_course_lapin(info: Info, match_id: int) -> MatchType:
        return services.lancer_course_lapin(get_current_user(info), match_id)

    @strawberry.mutation
    def defier_joueur_rps(info: Info, invite_id: int, score_cible: int = 3) -> RpsChallengeType:
        challenge = services.defier_joueur(get_current_user(info), invite_id, score_cible=score_cible)
        return RpsChallengeType(
            id=challenge["id"],
            from_id=challenge["from_id"],
            from_pseudo=challenge["from_pseudo"],
            to_id=challenge["to_id"],
            score_cible=challenge.get("score_cible", 3),
            created=challenge["created"],
        )

    @strawberry.mutation
    def accepter_defi_rps(info: Info, challenge_id: strawberry.ID) -> RpsMatchType:
        match = services.accepter_defi(get_current_user(info), str(challenge_id))
        return RpsMatchType(
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
        )

    @strawberry.mutation
    def supprimer_match_rps(info: Info, match_id: str) -> bool:
        return services.supprimer_match_rps(get_current_user(info), match_id)

    @strawberry.mutation
    def jouer_coup_rps(info: Info, match_id: str, coup: str) -> RpsMatchType:
        match = services.jouer_coup(get_current_user(info), match_id, coup)
        return RpsMatchType(
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
            vainqueur_id=match.get("vainqueur_id"),
        )

    @strawberry.mutation
    def demarrer_revanche_rps(info: Info, match_id: str) -> RpsMatchType:
        match = services.demarrer_revanche(match_id)
        return RpsMatchType(
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

    @strawberry.mutation
    def defier_joueur_penalty(info: Info, data: PenaltyMatchInput) -> PenaltyChallengeType:
        utilisateur = info.context.request.user
        if not utilisateur.is_authenticated:
            raise PermissionDeniedError("Vous devez être connecté.")
        challenge = services.defier_joueur_penalty(utilisateur, data.invite_id, data.score_cible)
        return PenaltyChallengeType(
            id=challenge["id"],
            hote_id=challenge["hote_id"],
            hote_pseudo=challenge["hote_pseudo"],
            invite_id=challenge["invite_id"],
            invite_pseudo=challenge["invite_pseudo"],
            score_cible=challenge["score_cible"],
            statut=challenge["statut"],
        )

    @strawberry.mutation
    def accepter_defi_penalty(info: Info, challenge_id: str) -> PenaltyMatchType:
        utilisateur = info.context.request.user
        if not utilisateur.is_authenticated:
            raise PermissionDeniedError("Vous devez être connecté.")
        match = services.accepter_defi_penalty(utilisateur, challenge_id)
        return PenaltyMatchType(
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

    @strawberry.mutation
    def jouer_tir_penalty(info: Info, match_id: str, direction: str) -> PenaltyMatchType:
        utilisateur = info.context.request.user
        if not utilisateur.is_authenticated:
            raise PermissionDeniedError("Vous devez être connecté.")
        match = services.jouer_tir_penalty(utilisateur, match_id, direction)
        return PenaltyMatchType(
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

    @strawberry.mutation
    def demarrer_revanche_penalty(info: Info, match_id: str) -> PenaltyMatchType:
        utilisateur = info.context.request.user
        if not utilisateur.is_authenticated:
            raise PermissionDeniedError("Vous devez être connecté.")
        match = services.demarrer_revanche_penalty(match_id)
        return PenaltyMatchType(
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

    @strawberry.mutation
    def supprimer_match_penalty(info: Info, match_id: str) -> bool:
        utilisateur = info.context.request.user
        if not utilisateur.is_authenticated:
            raise PermissionDeniedError("Vous devez être connecté.")
        return services.supprimer_match_penalty(utilisateur, match_id)