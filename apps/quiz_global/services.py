from __future__ import annotations

import random
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.quiz_global.errors import (
    AnswerRejectedError,
    GameNotJoinableError,
    MatchNotFoundError,
    NotYourTurnError,
    QuizGlobalError,
    ThemeUnavailableError,
    ValidationError,
)
from apps.quiz_global.models import (
    QuizGlobalGame,
    QuizGlobalGameQuestion,
    QuizGlobalPlayer,
    QuizGlobalPlayerAnswer,
)
from apps.themes.models import Question, Reponse, Theme
from apps.social.models import Notification, Publication
from apps.social.services import envoyer_notification

READING_DURATION = timedelta(seconds=10)
ANSWERING_DURATION = timedelta(seconds=10)
RESULT_DURATION = timedelta(seconds=5)
TARGET_ALLOWED = {4, 8, 12}
OPTION_LETTERS = ("A", "B", "C", "D")


def _broadcast(game_id: int, payload: dict, user_id: int | None = None) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    group = f"quiz_global_{game_id}" if user_id is None else f"quiz_global_{game_id}_u_{user_id}"
    try:
        async_to_sync(channel_layer.group_send)(group, {"type": "quiz.event", "data": payload})
    except Exception:
        return


def _schedule_tick(game_id: int, when) -> None:
    delay = max(0, int((when - timezone.now()).total_seconds()))
    try:
        from apps.quiz_global.tasks import quiz_global_tick

        quiz_global_tick.apply_async(args=[game_id], countdown=max(delay, 1))
    except Exception:
        return


def _player_map(game: QuizGlobalGame) -> dict[str, QuizGlobalPlayer]:
    return {p.seat: p for p in game.players.select_related("player").all()}


def _get_player(game: QuizGlobalGame, user) -> QuizGlobalPlayer:
    player = game.players.filter(player=user).select_related("player").first()
    if player is None:
        raise QuizGlobalError("Vous ne participez pas à cette partie.")
    return player


def _current_question(game: QuizGlobalGame) -> QuizGlobalGameQuestion | None:
    return (
        game.game_questions.select_related(
            "question",
            "theme",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
        )
        .order_by("-turn_number")
        .first()
    )


def available_questions_qs(game: QuizGlobalGame, theme: Theme):
    used_ids = list(QuizGlobalGameQuestion.objects.filter(game=game).values_list("question_id", flat=True))
    return (
        Question.objects.filter(theme=theme, validee=True)
        .exclude(id__in=used_ids)
        .annotate(wrong_count=Count("reponses", filter=Q(reponses__est_correcte=False)))
        .filter(wrong_count__gte=3)
        .prefetch_related("reponses")
    )


def theme_availability(game: QuizGlobalGame) -> list[dict]:
    # Le thème "Course lapin" appartient au jeu de matchs (course de lapins),
    # il est volontairement exclu du Quizz global.
    themes = Theme.objects.filter(actif=True).exclude(slug="course-lapin").order_by("nom")
    items = []
    for theme in themes:
        remaining = available_questions_qs(game, theme).count()
        items.append(
            {
                "id": theme.pk,
                "nom": theme.nom,
                "icone": theme.icone,
                "remaining": remaining,
                "selectable": remaining > 0,
            }
        )
    return items


def pick_random_question(qs) -> Question:
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        raise ThemeUnavailableError()
    return Question.objects.prefetch_related("reponses").get(pk=random.choice(ids))


def build_options(question: Question) -> tuple[list[Reponse], str]:
    reponses = list(question.reponses.all())
    correct = next((r for r in reponses if r.est_correcte), None)
    wrong = [r for r in reponses if not r.est_correcte and r.pk != getattr(correct, "pk", None)]
    if correct is None or len(wrong) < 3:
        raise ThemeUnavailableError("Cette question n'a pas assez de propositions.")
    selected_wrong = random.sample(wrong, 3)
    options = [correct, *selected_wrong]
    random.shuffle(options)
    correct_letter = OPTION_LETTERS[options.index(correct)]
    return options, correct_letter


def weighted_theme(game: QuizGlobalGame) -> Theme:
    weights = []
    themes = []
    for item in theme_availability(game):
        if item["remaining"] <= 0:
            continue
        themes.append(item["id"])
        weights.append(item["remaining"])
    if not themes:
        raise QuizGlobalError("Plus aucune question disponible pour le Tie-Break.")
    chosen_id = random.choices(themes, weights=weights, k=1)[0]
    return Theme.objects.get(pk=chosen_id)


def serialize_game(game: QuizGlobalGame, viewer=None) -> dict:
    now = timezone.now()
    players = _player_map(game)
    player_a = players.get("A")
    player_b = players.get("B")
    gq = _current_question(game)
    viewer_player = None
    if viewer is not None:
        viewer_player = next((p for p in players.values() if p.player_id == viewer.pk), None)

    payload = {
        "event": "STATE",
        "gameId": game.pk,
        "status": game.status,
        "targetQuestions": game.target_questions,
        "currentTurn": game.current_turn,
        "activeSeat": game.active_seat,
        "isTieBreak": game.status == QuizGlobalGame.Status.TIE_BREAK or bool(gq and gq.is_tie_break and not gq.finished_at),
        "phaseStartedAt": game.phase_started_at.isoformat() if game.phase_started_at else None,
        "phaseDeadline": game.phase_deadline.isoformat() if game.phase_deadline else None,
        "serverTime": now.isoformat(),
        "themes": theme_availability(game) if game.status == QuizGlobalGame.Status.THEME_SELECTION else [],
        "playerA": None
        if player_a is None
        else {
            "id": str(player_a.player_id),
            "pseudo": player_a.player.pseudo,
            "seat": "A",
            "score": player_a.score,
        },
        "playerB": None
        if player_b is None
        else {
            "id": str(player_b.player_id),
            "pseudo": player_b.player.pseudo,
            "seat": "B",
            "score": player_b.score,
        },
        "winnerId": str(game.winner_id) if game.winner_id else None,
        "question": None,
        "myAnswer": None,
        "mySeat": viewer_player.seat if viewer_player else None,
        "invitedPlayer": None
        if game.invited_player is None
        else {
            "id": str(game.invited_player_id),
            "pseudo": game.invited_player.pseudo,
            "seat": "",
            "score": 0,
        },
    }

    if gq is not None:
        show_options = game.status in (
            QuizGlobalGame.Status.ANSWERING,
            QuizGlobalGame.Status.QUESTION_FINISHED,
            QuizGlobalGame.Status.FINISHED,
        )
        show_result = game.status in (QuizGlobalGame.Status.QUESTION_FINISHED, QuizGlobalGame.Status.FINISHED) or bool(
            gq.finished_at
        )
        options = {
            "A": gq.option_a.texte,
            "B": gq.option_b.texte,
            "C": gq.option_c.texte,
            "D": gq.option_d.texte,
        }
        question_view = {
            "id": gq.pk,
            "turnNumber": gq.turn_number,
            "theme": gq.theme.nom,
            "question": gq.question.texte,
            "isTieBreak": gq.is_tie_break,
            "options": options if show_options else None,
            "correctOption": gq.correct_option if show_result else None,
            "correctText": getattr(gq, f"option_{gq.correct_option.lower()}").texte if show_result else None,
        }
        payload["question"] = question_view

        if viewer is not None:
            mine = gq.player_answers.filter(player=viewer).first()
            if mine is not None:
                status = "LOCKED"
                if game.status == QuizGlobalGame.Status.ANSWERING and not mine.is_correct:
                    status = "INCORRECT"
                elif show_result:
                    status = "CORRECT" if mine.is_correct else "INCORRECT"
                payload["myAnswer"] = {
                    "selectedOption": mine.selected_option,
                    "status": status,
                    "pointsAwarded": mine.points_awarded if show_result else None,
                }

        if show_result:
            results = []
            for seat, pl in (("A", player_a), ("B", player_b)):
                if pl is None:
                    continue
                ans = gq.player_answers.filter(player=pl.player).first()
                results.append(
                    {
                        "seat": seat,
                        "pseudo": pl.player.pseudo,
                        "selectedOption": ans.selected_option if ans else None,
                        "isCorrect": bool(ans and ans.is_correct),
                        "pointsAwarded": ans.points_awarded if ans else 0,
                    }
                )
            payload["results"] = results

    return payload


def _notify(game: QuizGlobalGame, event: str, extra: dict | None = None) -> None:
    for player in game.players.select_related("player"):
        data = serialize_game(game, player.player)
        data["event"] = event
        if extra:
            data.update(extra)
        _broadcast(game.pk, data, user_id=player.player_id)


@transaction.atomic
def create_game(user, target_questions: int, invite_id: int | None = None) -> QuizGlobalGame:
    if target_questions not in TARGET_ALLOWED:
        raise ValidationError("Le nombre de questions doit être 4, 8 ou 12.")
    invited = None
    if invite_id:
        from apps.users.models import Utilisateur

        invited = Utilisateur.objects.filter(pk=invite_id).first()
        if invited is None or invited.pk == user.pk:
            raise ValidationError("Adversaire invalide.")
    game = QuizGlobalGame.objects.create(
        target_questions=target_questions,
        invited_player=invited,
        status=QuizGlobalGame.Status.WAITING,
    )
    QuizGlobalPlayer.objects.create(game=game, player=user, seat="A")
    _notify(game, "GAME_CREATED")
    if invited is not None:
        envoyer_notification(
            invited,
            Notification.Type.DEFI_RECU,
            "Invitation Quizz Global",
            f"{user.pseudo} vous invite à un duel Quizz Global de {target_questions} questions.",
            reference_id=game.pk,
            expediteur=user,
        )
    else:
        publish_open_game(user, game)
    return game


def publish_open_game(user, game: QuizGlobalGame) -> Publication:
    """Publie un salon ouvert (sans invitation ciblée) dans le fil d'actualité."""
    return Publication.objects.create(
        auteur=user,
        texte=f"🎯 {user.pseudo} ouvre un salon Quizz Global ({game.target_questions} questions). Rejoignez-le !",
        lien_type="quiz_global",
        reference_id=game.pk,
    )


@transaction.atomic
def annuler_game(user, game_id: int) -> bool:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    if game.status != QuizGlobalGame.Status.WAITING:
        raise QuizGlobalError("Seules les parties en attente peuvent être annulées.")
    player = game.players.filter(player=user).first()
    if player is None:
        raise QuizGlobalError("Vous ne participez pas à cette partie.")
    if player.seat != "A":
        raise QuizGlobalError("Seul le créateur de la partie peut l'annuler.")
    invited = game.invited_player
    game.status = QuizGlobalGame.Status.CANCELLED
    game.invited_player = None
    game.save(update_fields=["status", "invited_player"])
    _notify(game, "GAME_CANCELLED")
    if invited is not None and invited.pk != user.pk:
        envoyer_notification(
            invited,
            Notification.Type.SYSTEME,
            "Invitation annulée",
            f"{user.pseudo} a annulé sa partie Quizz Global.",
            reference_id=game.pk,
            expediteur=user,
        )
    return True


@transaction.atomic
def refuser_invitation(user, game_id: int) -> bool:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    if game.status != QuizGlobalGame.Status.WAITING or game.invited_player_id != user.pk:
        raise QuizGlobalError("Aucune invitation en attente pour cette partie.")
    host = game.players.filter(seat="A").select_related("player").first()
    game.status = QuizGlobalGame.Status.CANCELLED
    game.invited_player = None
    game.save(update_fields=["status", "invited_player"])
    _notify(game, "INVITATION_REFUSED")
    if host is not None:
        envoyer_notification(
            host.player,
            Notification.Type.SYSTEME,
            "Invitation refusée",
            f"{user.pseudo} a refusé votre invitation Quizz Global.",
            reference_id=game.pk,
            expediteur=user,
        )
    return True


@transaction.atomic
def join_game(user, game_id: int) -> QuizGlobalGame:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    if game.status != QuizGlobalGame.Status.WAITING:
        raise GameNotJoinableError()
    if game.players.filter(player=user).exists():
        raise GameNotJoinableError("Vous êtes déjà dans cette partie.")
    if game.invited_player_id and game.invited_player_id != user.pk:
        raise GameNotJoinableError("Cette partie est réservée à un autre joueur.")
    if game.players.count() >= 2:
        raise GameNotJoinableError()
    QuizGlobalPlayer.objects.create(game=game, player=user, seat="B")
    now = timezone.now()
    game.status = QuizGlobalGame.Status.THEME_SELECTION
    game.started_at = now
    game.phase_started_at = now
    game.phase_deadline = None
    game.active_seat = "A"
    game.save()
    _notify(game, "PLAYER_JOINED")
    _notify(game, "GAME_STARTED")
    _notify(game, "THEME_SELECTION_STARTED")
    return game


def _lock_game(game_id: int) -> QuizGlobalGame:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    return game


def _create_game_question(game: QuizGlobalGame, theme: Theme, is_tie_break: bool) -> QuizGlobalGameQuestion:
    qs = available_questions_qs(game, theme)
    question = pick_random_question(qs)
    options, correct_letter = build_options(question)
    now = timezone.now()
    game.current_turn += 1
    gq = QuizGlobalGameQuestion.objects.create(
        game=game,
        question=question,
        theme=theme,
        turn_number=game.current_turn,
        option_a=options[0],
        option_b=options[1],
        option_c=options[2],
        option_d=options[3],
        correct_option=correct_letter,
        is_tie_break=is_tie_break,
        reading_started_at=now,
    )
    game.status = QuizGlobalGame.Status.QUESTION_READING
    game.phase_started_at = now
    game.phase_deadline = now + READING_DURATION
    game.save()
    _notify(game, "THEME_SELECTED", extra={"chosenTheme": theme.nom, "chosenBySeat": game.active_seat})
    _notify(game, "QUESTION_READING_STARTED")
    _schedule_tick(game.pk, game.phase_deadline)
    return gq


@transaction.atomic
def select_theme(user, game_id: int, theme_id: int) -> QuizGlobalGame:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    if game.status != QuizGlobalGame.Status.THEME_SELECTION:
        raise QuizGlobalError("Ce n'est pas le moment de choisir un thème.")
    if player.seat != game.active_seat:
        raise NotYourTurnError()
    theme = Theme.objects.filter(pk=theme_id, actif=True).first()
    if theme is None or theme.slug == "course-lapin":
        raise ThemeUnavailableError()
    if available_questions_qs(game, theme).count() == 0:
        raise ThemeUnavailableError()
    _create_game_question(game, theme, is_tie_break=False)
    return game


@transaction.atomic
def submit_answer(user, game_id: int, game_question_id: int, selected_option: str) -> dict:
    game = _lock_game(game_id)
    player = _get_player(game, user)
    option = (selected_option or "").upper()
    if option not in OPTION_LETTERS:
        raise AnswerRejectedError("Option invalide.")
    if game.status != QuizGlobalGame.Status.ANSWERING:
        raise AnswerRejectedError("Ce n'est pas la phase de réponse.")
    now = timezone.now()
    if game.phase_deadline and now > game.phase_deadline:
        raise AnswerRejectedError("Le temps est écoulé.")
    gq = QuizGlobalGameQuestion.objects.select_for_update().filter(pk=game_question_id, game=game).first()
    if gq is None or gq.finished_at:
        raise AnswerRejectedError("Question invalide.")
    if QuizGlobalPlayerAnswer.objects.filter(game_question=gq, player=user).exists():
        raise AnswerRejectedError("Vous avez déjà répondu.")
    is_correct = option == gq.correct_option
    answer = QuizGlobalPlayerAnswer.objects.create(
        game_question=gq,
        player=user,
        selected_option=option,
        is_correct=is_correct,
        points_awarded=0,
        answered_at=now,
    )
    ack = {
        "event": "PLAYER_ANSWER_ACK",
        "gameQuestionId": gq.pk,
        "selectedOption": option,
        "status": "INCORRECT" if not is_correct else "RECORDED",
    }
    _broadcast(game.pk, ack, user_id=user.pk)
    return {"ok": True, "status": ack["status"], "answerId": answer.pk}


def _start_answering(game: QuizGlobalGame) -> None:
    gq = _current_question(game)
    if gq is None:
        return
    now = timezone.now()
    game.status = QuizGlobalGame.Status.ANSWERING
    game.phase_started_at = now
    game.phase_deadline = now + ANSWERING_DURATION
    gq.answering_started_at = now
    gq.answer_deadline = game.phase_deadline
    gq.save(update_fields=["answering_started_at", "answer_deadline"])
    game.save()
    _notify(game, "ANSWERING_STARTED")
    _schedule_tick(game.pk, game.phase_deadline)


def _finish_question(game: QuizGlobalGame) -> None:
    gq = _current_question(game)
    if gq is None or gq.finished_at:
        return
    now = timezone.now()
    gq.finished_at = now
    gq.save(update_fields=["finished_at"])
    players = _player_map(game)
    for pl in players.values():
        ans = QuizGlobalPlayerAnswer.objects.filter(game_question=gq, player=pl.player).first()
        if ans and ans.is_correct:
            ans.points_awarded = 1
            ans.save(update_fields=["points_awarded"])
            pl.score += 1
            pl.save(update_fields=["score"])
    game.status = QuizGlobalGame.Status.QUESTION_FINISHED
    game.phase_started_at = now
    game.phase_deadline = now + RESULT_DURATION
    game.save()
    _notify(game, "QUESTION_FINISHED")
    _notify(game, "SCORE_UPDATED")
    _schedule_tick(game.pk, game.phase_deadline)


def _advance_after_result(game: QuizGlobalGame) -> None:
    gq = _current_question(game)
    players = _player_map(game)
    score_a = players["A"].score if "A" in players else 0
    score_b = players["B"].score if "B" in players else 0
    normal_done = QuizGlobalGameQuestion.objects.filter(game=game, is_tie_break=False, finished_at__isnull=False).count()

    if gq and gq.is_tie_break:
        if score_a != score_b:
            _finish_game(game, score_a, score_b)
            return
        try:
            _start_tie_break_question(game)
        except QuizGlobalError:
            _finish_game(game, score_a, score_b, draw=True)
        return

    if normal_done < game.target_questions:
        game.active_seat = "B" if game.active_seat == "A" else "A"
        game.status = QuizGlobalGame.Status.THEME_SELECTION
        game.phase_started_at = timezone.now()
        game.phase_deadline = None
        game.save()
        _notify(game, "NEXT_TURN")
        _notify(game, "THEME_SELECTION_STARTED")
        return

    if score_a == score_b:
        game.status = QuizGlobalGame.Status.TIE_BREAK
        game.save()
        _notify(game, "TIE_BREAK_STARTED")
        try:
            _start_tie_break_question(game)
        except QuizGlobalError:
            _finish_game(game, score_a, score_b, draw=True)
        return
    _finish_game(game, score_a, score_b)


def _start_tie_break_question(game: QuizGlobalGame) -> None:
    theme = weighted_theme(game)
    _create_game_question(game, theme, is_tie_break=True)


def _finish_game(game: QuizGlobalGame, score_a: int, score_b: int, draw: bool = False) -> None:
    players = _player_map(game)
    winner = None
    if not draw:
        if score_a > score_b:
            winner = players["A"].player
        elif score_b > score_a:
            winner = players["B"].player
    game.winner = winner
    game.status = QuizGlobalGame.Status.FINISHED
    game.finished_at = timezone.now()
    game.phase_deadline = None
    game.save()
    _notify(game, "GAME_FINISHED")


@transaction.atomic
def tick(game_id: int) -> QuizGlobalGame | None:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        return None
    now = timezone.now()
    if game.phase_deadline and now < game.phase_deadline:
        return game
    if game.status == QuizGlobalGame.Status.QUESTION_READING:
        _start_answering(game)
    elif game.status == QuizGlobalGame.Status.ANSWERING:
        _finish_question(game)
    elif game.status == QuizGlobalGame.Status.QUESTION_FINISHED:
        _advance_after_result(game)
    return game


def list_waiting_games():
    return (
        QuizGlobalGame.objects.filter(status=QuizGlobalGame.Status.WAITING, invited_player__isnull=True)
        .select_related("invited_player")
        .prefetch_related("players__player")
        .order_by("-cree_le")
    )


def list_my_games(user):
    return (
        QuizGlobalGame.objects.filter(players__player=user)
        .exclude(status__in=[QuizGlobalGame.Status.FINISHED, QuizGlobalGame.Status.CANCELLED])
        .select_related("invited_player")
        .prefetch_related("players__player")
        .distinct()
        .order_by("-cree_le")
    )


def mes_invitations(user):
    return (
        QuizGlobalGame.objects.filter(status=QuizGlobalGame.Status.WAITING, invited_player=user)
        .select_related("invited_player")
        .prefetch_related("players__player")
        .order_by("-cree_le")
    )


def get_game(game_id: int) -> QuizGlobalGame:
    game = (
        QuizGlobalGame.objects.filter(pk=game_id)
        .select_related("invited_player")
        .prefetch_related("players__player")
        .first()
    )
    if game is None:
        raise MatchNotFoundError()
    return game
