import strawberry
from strawberry.types import Info

from apps.quiz_global import services
from apps.quiz_global.types import QuizGlobalState, to_state
from common.graphql.permissions import get_current_user


@strawberry.type
class QuizGlobalQuery:
    @strawberry.field
    def parties_quiz_global_disponibles(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        return [to_state(game, user) for game in services.list_waiting_games()]

    @strawberry.field
    def mes_parties_quiz_global(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        return [to_state(game, user) for game in services.list_my_games(user)]

    @strawberry.field
    def partie_quiz_global(self, info: Info, game_id: int) -> QuizGlobalState:
        user = get_current_user(info)
        return to_state(services.get_game(game_id), user)

    @strawberry.field
    def mes_invitations_quiz_global(self, info: Info) -> list[QuizGlobalState]:
        user = get_current_user(info)
        return [to_state(game, user) for game in services.mes_invitations(user)]
