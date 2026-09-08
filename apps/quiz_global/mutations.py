import strawberry
from decimal import Decimal
from strawberry.types import Info

from apps.quiz_global import services
from apps.quiz_global.types import QuizGlobalState, to_state
from common.graphql.permissions import get_current_user


@strawberry.type
class QuizGlobalAnswerResult:
    ok: bool
    status: str


@strawberry.type
class QuizGlobalMutation:
    @strawberry.mutation
    def creer_partie_quiz_global(self, info: Info, target_questions: int, invite_id: int | None = None, mise: Decimal = Decimal("0")) -> QuizGlobalState:
        user = get_current_user(info)
        game = services.create_game(user, target_questions, invite_id, mise)
        return to_state(game, user)

    @strawberry.mutation
    def rejoindre_partie_quiz_global(self, info: Info, game_id: int, mise: Decimal | None = None) -> QuizGlobalState:
        user = get_current_user(info)
        game = services.join_game(user, game_id, mise)
        return to_state(game, user)

    @strawberry.mutation
    def choisir_theme_quiz_global(self, info: Info, game_id: int, theme_id: int) -> QuizGlobalState:
        user = get_current_user(info)
        game = services.select_theme(user, game_id, theme_id)
        return to_state(game, user)

    @strawberry.mutation
    def repondre_quiz_global(self, info: Info, game_id: int, game_question_id: int, selected_option: str) -> QuizGlobalAnswerResult:
        user = get_current_user(info)
        result = services.submit_answer(user, game_id, game_question_id, selected_option)
        return QuizGlobalAnswerResult(ok=result["ok"], status=result["status"])

    @strawberry.mutation
    def avancer_phase_quiz_global(self, info: Info, game_id: int) -> QuizGlobalState:
        """Avance la phase si le délai serveur est atteint (reconnexion / rattrapage)."""
        user = get_current_user(info)
        game = services.tick(game_id)
        return to_state(game or services.get_game(game_id), user)

    @strawberry.mutation
    def annuler_partie_quiz_global(self, info: Info, game_id: int) -> bool:
        """Annule une partie Quizz Global encore en attente (créateur uniquement)."""
        user = get_current_user(info)
        return services.annuler_game(user, game_id)

    @strawberry.mutation
    def refuser_invitation_quiz_global(self, info: Info, game_id: int) -> bool:
        """Refuse une invitation Quizz Global reçue."""
        user = get_current_user(info)
        return services.refuser_invitation(user, game_id)

    @strawberry.mutation
    def revanche_partie_quiz_global(self, info: Info, game_id: int) -> QuizGlobalState:
        """Recrée une partie immédiate contre le même adversaire après une partie terminée."""
        user = get_current_user(info)
        game = services.revanche_game(user, game_id)
        return to_state(game, user)
