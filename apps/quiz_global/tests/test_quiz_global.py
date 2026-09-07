import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.quiz_global.errors import AnswerRejectedError, NotYourTurnError, QuizGlobalError, ThemeUnavailableError
from apps.quiz_global.models import QuizGlobalGame, QuizGlobalGameQuestion, QuizGlobalPlayerAnswer
from apps.quiz_global.services import create_game, join_game, revanche_game, select_theme, serialize_game, submit_answer, tick
from apps.themes.models import Theme
from apps.users.models import Utilisateur


def _user(email, pseudo):
    return Utilisateur.objects.create_user(email=email, pseudo=pseudo, password="MotDePasse1!")


def _start_pair(target=4):
    a = _user("a@quiz.mg", "AliceQ")
    b = _user("b@quiz.mg", "BobQ")
    game = create_game(a, target)
    game = join_game(b, game.pk)
    return a, b, game


def _expire(game):
    game.phase_deadline = timezone.now() - timedelta(seconds=1)
    game.save(update_fields=["phase_deadline"])
    return tick(game.pk)


@pytest.fixture(autouse=True)
def seed_q():
    call_command("seed_questions", verbosity=0)


@pytest.mark.django_db
def test_create_join_and_theme_selection():
    a, b, game = _start_pair()
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.THEME_SELECTION
    assert game.active_seat == "A"
    theme = Theme.objects.filter(actif=True).first()
    with pytest.raises(NotYourTurnError):
        select_theme(b, game.pk, theme.pk)
    select_theme(a, game.pk, theme.pk)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.QUESTION_READING
    gq = QuizGlobalGameQuestion.objects.get(game=game)
    assert gq.correct_option in "ABCD"
    payload = serialize_game(game, a)
    assert payload["question"]["options"] is None
    assert payload["question"]["correctOption"] is None


@pytest.mark.django_db
def test_answering_hides_correct_and_opponent():
    a, b, game = _start_pair()
    theme = Theme.objects.filter(actif=True).first()
    select_theme(a, game.pk, theme.pk)
    _expire(game)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.ANSWERING
    gq = QuizGlobalGameQuestion.objects.get(game=game)
    payload = serialize_game(game, a)
    assert payload["question"]["options"] is not None
    assert payload["question"]["correctOption"] is None
    submit_answer(a, game.pk, gq.pk, gq.correct_option)
    payload_b = serialize_game(game, b)
    assert payload_b["myAnswer"] is None
    with pytest.raises(AnswerRejectedError):
        submit_answer(a, game.pk, gq.pk, "A")


@pytest.mark.django_db
def test_wrong_answer_blocks_player_and_both_can_score():
    a, b, game = _start_pair()
    theme = Theme.objects.filter(actif=True).first()
    select_theme(a, game.pk, theme.pk)
    _expire(game)
    gq = QuizGlobalGameQuestion.objects.get(game=game)
    wrong = next(letter for letter in "ABCD" if letter != gq.correct_option)
    result = submit_answer(a, game.pk, gq.pk, wrong)
    assert result["status"] == "INCORRECT"
    submit_answer(b, game.pk, gq.pk, gq.correct_option)
    _expire(game)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.QUESTION_FINISHED
    payload = serialize_game(game, a)
    assert payload["playerA"]["score"] == 0
    assert payload["playerB"]["score"] == 1
    assert payload["question"]["correctOption"] == gq.correct_option


@pytest.mark.django_db
def test_question_never_reused_in_same_game():
    a, b, game = _start_pair(target=4)
    used = []
    for i in range(4):
        game.refresh_from_db()
        if game.status == QuizGlobalGame.Status.QUESTION_FINISHED:
            _expire(game)
            game.refresh_from_db()
        theme = Theme.objects.filter(actif=True).first()
        actor = a if game.active_seat == "A" else b
        select_theme(actor, game.pk, theme.pk)
        gq = QuizGlobalGameQuestion.objects.filter(game=game).order_by("-turn_number").first()
        used.append(gq.question_id)
        _expire(game)
        _expire(game)
    assert len(used) == len(set(used))


@pytest.mark.django_db
def test_tie_break_until_winner():
    a, b, game = _start_pair(target=4)
    for _ in range(4):
        game.refresh_from_db()
        if game.status == QuizGlobalGame.Status.QUESTION_FINISHED:
            _expire(game)
            game.refresh_from_db()
        theme = Theme.objects.filter(actif=True).first()
        actor = a if game.active_seat == "A" else b
        select_theme(actor, game.pk, theme.pk)
        _expire(game)
        _expire(game)
    game.refresh_from_db()
    assert QuizGlobalGameQuestion.objects.filter(game=game, is_tie_break=False).count() == 4
    _expire(game)
    game.refresh_from_db()
    assert QuizGlobalGameQuestion.objects.filter(game=game, is_tie_break=True).exists()
    gq = QuizGlobalGameQuestion.objects.filter(game=game, is_tie_break=True).order_by("-turn_number").first()
    if game.status == QuizGlobalGame.Status.QUESTION_READING:
        _expire(game)
    game.refresh_from_db()
    submit_answer(a, game.pk, gq.pk, gq.correct_option)
    wrong = next(letter for letter in "ABCD" if letter != gq.correct_option)
    submit_answer(b, game.pk, gq.pk, wrong)
    _expire(game)
    game.refresh_from_db()
    _expire(game)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.FINISHED
    assert game.winner_id == a.pk


@pytest.mark.django_db
def test_tie_break_draw_when_no_question_available(monkeypatch):
    from apps.quiz_global import services as quiz_services

    a, b, game = _start_pair(target=4)

    def _both_correct_turn():
        game.refresh_from_db()
        if game.status == QuizGlobalGame.Status.QUESTION_FINISHED:
            _expire(game)
            game.refresh_from_db()
        theme = Theme.objects.filter(actif=True).first()
        actor = a if game.active_seat == "A" else b
        select_theme(actor, game.pk, theme.pk)
        gq = QuizGlobalGameQuestion.objects.filter(game=game).order_by("-turn_number").first()
        _expire(game)
        game.refresh_from_db()
        submit_answer(a, game.pk, gq.pk, gq.correct_option)
        submit_answer(b, game.pk, gq.pk, gq.correct_option)
        _expire(game)
        _expire(game)
        game.refresh_from_db()

    monkeypatch.setattr(
        quiz_services,
        "weighted_theme",
        lambda game: (_ for _ in ()).throw(QuizGlobalError("Plus aucune question disponible pour le Tie-Break.")),
    )

    for _ in range(4):
        _both_correct_turn()
    assert game.status == QuizGlobalGame.Status.FINISHED
    assert game.winner_id is None


@pytest.mark.django_db
def test_graphql_quiz_global_flow(client):
    def gql(query, token=None):
        kwargs = {"content_type": "application/json"}
        if token:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        r = client.post("/graphql/", data={"query": query}, **kwargs)
        return json.loads(r.content)

    def register(email, pseudo):
        resp = gql(
            f'mutation {{ register(input: {{ email: "{email}", pseudo: "{pseudo}", password: "MotDePasse1!" }}) {{ accessToken }} }}'
        )
        assert "errors" not in resp, resp
        return resp["data"]["register"]["accessToken"]

    tok_a = register("ga@quiz.mg", "Gala")
    tok_b = register("gb@quiz.mg", "GalaB")
    created = gql("mutation { creerPartieQuizGlobal(targetQuestions: 4) { gameId status targetQuestions } }", tok_a)
    assert "errors" not in created, created
    game_id = created["data"]["creerPartieQuizGlobal"]["gameId"]
    joined = gql(f"mutation {{ rejoindrePartieQuizGlobal(gameId: {game_id}) {{ status activeSeat }} }}", tok_b)
    assert joined["data"]["rejoindrePartieQuizGlobal"]["status"] == "THEME_SELECTION"
    theme = Theme.objects.filter(actif=True).first()
    chosen = gql(
        f"mutation {{ choisirThemeQuizGlobal(gameId: {game_id}, themeId: {theme.pk}) {{ status question {{ correctOption options {{ A }} }} }} }}",
        tok_a,
    )
    assert "errors" not in chosen, chosen
    assert chosen["data"]["choisirThemeQuizGlobal"]["status"] == "QUESTION_READING"
    assert chosen["data"]["choisirThemeQuizGlobal"]["question"]["correctOption"] is None
    assert chosen["data"]["choisirThemeQuizGlobal"]["question"]["options"] is None


@pytest.mark.django_db
def test_revanche_reattaches_same_players():
    a, b, game = _start_pair(target=8)
    game.status = QuizGlobalGame.Status.FINISHED
    game.save(update_fields=["status"])
    new_game = revanche_game(a, game.pk)
    new_game.refresh_from_db()
    assert new_game.status == QuizGlobalGame.Status.THEME_SELECTION
    assert new_game.target_questions == 8
    seats = {p.seat: p.player_id for p in new_game.players.all()}
    assert seats == {"A": a.pk, "B": b.pk}


@pytest.mark.django_db
def test_revanche_rejects_non_finished_and_outsiders():
    a, _, game = _start_pair()
    with pytest.raises(QuizGlobalError):
        revanche_game(a, game.pk)
    stranger = _user("stranger@quiz.mg", "StrangerQ")
    game.status = QuizGlobalGame.Status.FINISHED
    game.save(update_fields=["status"])
    with pytest.raises(QuizGlobalError):
        revanche_game(stranger, game.pk)


@pytest.mark.django_db
def test_graphql_revanche_partie_quiz_global(client):
    from apps.quiz_global.models import QuizGlobalGame as GameModel

    def gql(query, token=None):
        kwargs = {"content_type": "application/json"}
        if token:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        r = client.post("/graphql/", data={"query": query}, **kwargs)
        return json.loads(r.content)

    def register(email, pseudo):
        resp = gql(
            f'mutation {{ register(input: {{ email: "{email}", pseudo: "{pseudo}", password: "MotDePasse1!" }}) {{ accessToken }} }}'
        )
        assert "errors" not in resp, resp
        return resp["data"]["register"]["accessToken"]

    tok_a = register("ra@quiz.mg", "RevancheA")
    tok_b = register("rb@quiz.mg", "RevancheB")
    created = gql("mutation { creerPartieQuizGlobal(targetQuestions: 4) { gameId } }", tok_a)
    game_id = created["data"]["creerPartieQuizGlobal"]["gameId"]
    gql(f"mutation {{ rejoindrePartieQuizGlobal(gameId: {game_id}) {{ status }} }}", tok_b)
    GameModel.objects.filter(pk=game_id).update(status=GameModel.Status.FINISHED)
    revanche = gql(f"mutation {{ revanchePartieQuizGlobal(gameId: {game_id}) {{ gameId status targetQuestions }} }}", tok_a)
    assert "errors" not in revanche, revanche
    payload = revanche["data"]["revanchePartieQuizGlobal"]
    assert payload["status"] == "THEME_SELECTION"
    assert payload["targetQuestions"] == 4
    assert payload["gameId"] != game_id
