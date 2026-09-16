import logging

import strawberry
from strawberry.types import Info

from apps.quiz_global import services
from apps.quiz_global.active_game_service import get_active_game
from apps.quiz_global.types import (
    QuizGlobalPublicState,
    QuizGlobalState,
    to_public_state,
    to_state,
)
from common.graphql.permissions import get_current_user

logger = logging.getLogger(__name__)


@strawberry.type
class QuizGlobalQuery:
    @strawberry.field
    def parties_quiz_global_disponibles(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        result = []
        for game in services.list_waiting_games():
            try:
                result.append(to_state(game, user))
            except Exception:
                logger.exception("Erreur sérialisation salon disponible game_id=%s", game.pk)
        return result

    @strawberry.field
    def mes_parties_quiz_global(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        result = []
        for game in services.list_my_games(user):
            try:
                result.append(to_state(game, user))
            except Exception:
                logger.exception("Erreur sérialisation de mes parties game_id=%s", game.pk)
        return result

    @strawberry.field
    def my_active_game(self, info: Info) -> QuizGlobalState | None:
        """La partie réellement active du joueur (ou null si aucun).

        Une partie FINISHED/CANCELLED/EXPIRED/ABANDONED n'est jamais retournée :
        elle ne bloque plus le joueur.
        """
        user = get_current_user(info)
        game = get_active_game(user)
        if game is None:
            return None
        return to_state(game, user)

    @strawberry.field
    def parties_quiz_global_actives(self, info: Info) -> list[QuizGlobalPublicState]:
        """Toutes les parties démarrées et en cours, tous joueurs confondus.

        Résumé public (aucune question/option exposée) : permet d'afficher les
        parties actives au-dessus du lobby.
        """
        get_current_user(info)
        result = []
        for game in services.list_active_games():
            try:
                result.append(to_public_state(game))
            except Exception:
                logger.exception("Erreur sérialisation partie active game_id=%s", game.pk)
        return result

    @strawberry.field
    def partie_quiz_global(self, info: Info, game_id: int) -> QuizGlobalState:
        user = get_current_user(info)
        return to_state(services.get_game(game_id), user)

    @strawberry.field
    def mes_invitations_quiz_global(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        result = []
        try:
            for game in services.mes_invitations(user):
                try:
                    result.append(to_state(game, user))
                except Exception:
                    logger.exception("Erreur sérialisation invitation game_id=%s", game.pk)
        except Exception:
            logger.exception("Erreur lecture des invitations Quizz Global pour user=%s", user.pk)
        return result

    @strawberry.field
    def historique_parties_quiz_global(self, info: Info) -> list[QuizGlobalState]:
        """Toutes les parties du joueur, actives et historiques (avec détail)."""
        user = get_current_user(info)
        result = []
        for game in services.list_my_games_history(user):
            try:
                result.append(to_state(game, user))
            except Exception:
                logger.exception("Erreur sérialisation historique game_id=%s", game.pk)
        return result
