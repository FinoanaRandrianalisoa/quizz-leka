from __future__ import annotations

import logging
import random
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

from apps.betting.models import Pari  # noqa: F401
from apps.quiz_global.active_game_service import (
    accept_invitation,
    cancel_invitations,
    expire_invitations,
    get_active_game,
    has_active_game,
    release_players,
    reserve_player,
)
from apps.quiz_global.constants import INACTIVE_STATUSES
from apps.quiz_global.errors import (
    AnswerRejectedError,
    GameCancelledError,
    GameFullError,
    GameNotJoinableError,
    MatchNotFoundError,
    NotYourTurnError,
    PlayerAlreadyInGameError,
    QuizGlobalError,
    ThemeUnavailableError,
    ValidationError,
    validate_transition,
)
from apps.quiz_global.models import (
    QuizGlobalGame,
    QuizGlobalGameQuestion,
    QuizGlobalInvitation,
    QuizGlobalPlayer,
    QuizGlobalPlayerAnswer,
)
from apps.themes.models import Question, Reponse, Theme
from apps.social.models import Notification, Publication
from apps.social.services import envoyer_notification
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

READING_DURATION = timedelta(seconds=10)
ANSWERING_DURATION = timedelta(seconds=10)
RESULT_DURATION = timedelta(seconds=5)
TARGET_ALLOWED = {4, 8, 12}
OPTION_LETTERS = ("A", "B", "C", "D")
WAITING_EXPIRY_SECONDS = 30 * 60  # 30 minutes : salon qui ne rejoint personne -> EXPIRED
ABANDON_TIMEOUT_SECONDS = 120  # 2 minutes sans progression de phase -> ABANDONED


def _mise_reference(game_id: int, user_id: int) -> str:
    return f"mise-quiz-global-{game_id}-{user_id}"


def _sync_invitation_row(game: QuizGlobalGame, invite_id: int | None, sender) -> None:
    """Crée une ligne QuizGlobalInvitation pour l'invitation ciblée (migration progressive)."""
    if not invite_id or invite_id == sender.pk:
        return
    QuizGlobalInvitation.objects.get_or_create(
        game=game,
        receiver_id=invite_id,
        defaults={"sender": sender},
    )


def _invalidate_stale_invitations(game: QuizGlobalGame) -> None:
    """Invalide les invitations PENDING d'un salon à l'état inactif."""
    QuizGlobalInvitation.objects.filter(game=game, status=QuizGlobalInvitation.Status.PENDING).update(
        status=QuizGlobalInvitation.Status.EXPIRED,
    )


def _expire_peers(game: QuizGlobalGame, accepted_user) -> None:
    """Expire toutes les invitations PENDING du salon sauf celle du joueur accepté."""
    QuizGlobalInvitation.objects.filter(
        game=game,
        status=QuizGlobalInvitation.Status.PENDING,
    ).exclude(receiver=accepted_user).update(status=QuizGlobalInvitation.Status.EXPIRED)


def _valider_mise(montant, portefeuille) -> Decimal:
    value = Decimal(str(montant or 0)).quantize(Decimal("0.01"))
    if value < 0:
        raise ValidationError("Montant de mise invalide.")
    if value > portefeuille.solde_recharge:
        from common.graphql.errors import InsufficientFundsError

        raise InsufficientFundsError()
    return value


def mise_effective(game: QuizGlobalGame) -> Decimal:
    """Mise effectivement engagée : MIN(mise hôte, mise invité)."""
    if game.mise <= 0:
        return Decimal("0")
    invite = game.mise_proposee_invite if game.mise_proposee_invite is not None else game.mise
    if invite <= 0:
        return game.mise
    return min(game.mise, invite)


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
        "isTieBreak": game.status == QuizGlobalGame.Status.TIE_BREAK_THEME or bool(gq and gq.is_tie_break and not gq.finished_at),
        "phaseStartedAt": game.phase_started_at.isoformat() if game.phase_started_at else None,
        "phaseDeadline": game.phase_deadline.isoformat() if game.phase_deadline else None,
        "serverTime": now.isoformat(),
        "createdAt": game.cree_le.isoformat() if game.cree_le else None,
        "mise": f"{game.mise:.2f}",
        "miseEffective": f"{mise_effective(game):.2f}",
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
def create_game(user, target_questions: int, invite_id: int | None = None, mise: Decimal | None = None) -> QuizGlobalGame:
    if target_questions not in TARGET_ALLOWED:
        raise ValidationError("Le nombre de questions doit être 4, 8 ou 12.")
    invited = None
    if invite_id:
        from apps.users.models import Utilisateur

        invited = Utilisateur.objects.filter(pk=invite_id).first()
        if invited is None or invited.pk == user.pk:
            raise ValidationError("Adversaire invalide.")
    # ── Une seule partie réellement active par joueur ──
    # Le verrou est la table ActivePlayer (OneToOne) : interroger l'historique
    # (FINISHED/CANCELLED/EXPIRED/ABANDONED…) ne doit JAMAIS empêcher de créer.
    if has_active_game(user):
        raise PlayerAlreadyInGameError("Vous avez déjà une partie active. Terminez-la ou annulez-la d'abord.")
    if not hasattr(user, "portefeuille"):
        raise ValidationError("Portefeuille introuvable.")
    mise = _valider_mise(mise, user.portefeuille)
    game = QuizGlobalGame.objects.create(
        target_questions=target_questions,
        invited_player=invited,
        mise=mise,
        status=QuizGlobalGame.Status.WAITING,
    )
    QuizGlobalPlayer.objects.create(game=game, player=user, seat="A")
    reserve_player(user, game)
    _sync_invitation_row(game, invite_id, user)
    if mise > 0:
        wallet_services.bloquer_mise(
            user.portefeuille,
            mise,
            reference=_mise_reference(game.pk, user.pk),
            metadata={"game": game.pk, "role": "hote"},
            idempotency_key=f"reserve:{game.pk}:{user.pk}",
        )
    return game


def _after_create_game(game, user, invited, target_questions, mise):
    """Effets secondaires après création (notifications / broadcast).

    Appelé hors transaction pour ne pas compromettre la création du salon.
    """
    try:
        _notify(game, "GAME_CREATED")
    except Exception:
        logger.exception("Échec broadcast GAME_CREATED game=%s", game.pk)
    if invited is not None:
        try:
            logger.info(f"Envoi notification Quiz Global à {invited.pseudo} (id={invited.pk}) pour game={game.pk}")
            envoyer_notification(
                invited,
                Notification.Type.DEFI_RECU,
                "Invitation Quizz Global",
                f"{user.pseudo} vous invite à un duel Quizz Global de {target_questions} questions"
                + (f" (mise {mise} Ar)." if mise > 0 else "."),
                reference_id=game.pk,
                expediteur=user,
            )
            logger.info(f"Notification Quiz Global envoyée avec succès à {invited.pseudo}")
        except Exception:
            logger.exception("Échec notification invitation game=%s", game.pk)
    else:
        try:
            publish_open_game(user, game)
        except Exception:
            logger.exception("Échec publication salon ouvert game=%s", game.pk)


def publish_open_game(user, game: QuizGlobalGame) -> Publication:
    """Publie un salon ouvert (sans invitation ciblée) dans le fil d'actualité."""
    return Publication.objects.create(
        auteur=user,
        texte=(
            f"🎯 {user.pseudo} ouvre un salon Quizz Global ({game.target_questions} questions)."
            + (f" Mise {game.mise} Ar." if game.mise > 0 else " Rejoignez-le !")
        ),
        lien_type="quiz_global",
        reference_id=game.pk,
    )


def _liberer_mise_hote(game: QuizGlobalGame, motif: str = "annulation") -> None:
    """Rembourse la mise bloquée de l'hôte (salon jamais commencé)."""
    if game.mise <= 0:
        return
    host_player = game.players.filter(seat="A").select_related("player__portefeuille").first()
    if host_player is None or not hasattr(host_player.player, "portefeuille"):
        return
    wallet_services.liberer_mise(
        host_player.player.portefeuille,
        game.mise,
        type_=LedgerEntry.Type.REMBOURSEMENT,
        reference=f"remboursement-quiz-global-{game.pk}-{host_player.player.pk}",
        metadata={"game": game.pk, "motif": motif},
        idempotency_key=f"{motif}:{game.pk}:{host_player.player.pk}",
    )


@transaction.atomic
def _expirer_salon(game: QuizGlobalGame) -> None:
    """Expire un salon WAITING (expiration automatique). Row déjà verrouillée.

    Le statut passe à EXPIRED (inactif) : le joueur est libéré immédiatement
    et peut créer/rejoindre une nouvelle partie.
    """
    if game.status != QuizGlobalGame.Status.WAITING:
        return
    invited = game.invited_player
    host = game.players.filter(seat="A").select_related("player").first()
    validate_transition(game.status, QuizGlobalGame.Status.EXPIRED)
    game.status = QuizGlobalGame.Status.EXPIRED
    game.expired_at = timezone.now()
    game.invited_player = None
    game.save(update_fields=["status", "expired_at", "invited_player"])
    _liberer_mise_hote(game, motif="expiration")
    _invalidate_stale_invitations(game)
    release_players(game)
    _notify(game, "GAME_EXPIRED")
    if invited is not None:
        envoyer_notification(
            invited,
            Notification.Type.SYSTEME,
            "Salon Quizz Global expiré",
            f"L'invitation de {host.player.pseudo if host else 'l’hôte'} a expiré : "
            f"personne n'a rejoint la partie dans les temps.",
            reference_id=game.pk,
            expediteur=host.player if host else None,
        )


@transaction.atomic
def expirer_parties_en_attente(expiration_secondes: int = WAITING_EXPIRY_SECONDS) -> int:
    """Expire automatiquement les salons WAITING plus vieux que `expiration_secondes`.

    Le statut devient EXPIRED (inactif) : le joueur est libéré immédiatement.
    Appelé périodiquement (Celery beat) et paresseusement (list/get) pour garantir
    qu'aucun salon ne reste bloquant plus longtemps que la durée d'attente.
    """
    cutoff = timezone.now() - timedelta(seconds=expiration_secondes)
    expired_ids = list(
        QuizGlobalGame.objects.filter(
            status=QuizGlobalGame.Status.WAITING,
            cree_le__lt=cutoff,
        ).values_list("pk", flat=True)
    )
    for game_id in expired_ids:
        game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
        _expirer_salon(game)
    logger.info("Expiration salons Quizz Global : %d partie(s) expirée(s)", len(expired_ids))
    return len(expired_ids)


@transaction.atomic
def abandonner_parties_bloquees(grace_secondes: int = ABANDON_TIMEOUT_SECONDS) -> int:
    """Passe à ABANDONED les parties bloquées sans progression de phase.

    Une partie dont la `phase_deadline` est dépassée depuis longtemps (et qui
    n'a donc pas avancé) indique une déconnexion définitive d'un joueur : à
    partir de ce moment elle est INACTIVE et libère les deux joueurs.
    """
    cutoff = timezone.now() - timedelta(seconds=grace_secondes)
    stuck_ids = list(
        QuizGlobalGame.objects.filter(
            status__in=[
                QuizGlobalGame.Status.QUESTION_READING,
                QuizGlobalGame.Status.ANSWERING,
                QuizGlobalGame.Status.QUESTION_FINISHED,
                QuizGlobalGame.Status.TIE_BREAK_THEME,
            ],
            phase_deadline__isnull=False,
            phase_deadline__lt=cutoff,
            abandoned_at__isnull=True,
        ).values_list("pk", flat=True)
    )
    for game_id in stuck_ids:
        game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
        if game is None:
            continue
        validate_transition(game.status, QuizGlobalGame.Status.ABANDONED)
        game.status = QuizGlobalGame.Status.ABANDONED
        game.abandoned_at = timezone.now()
        game.phase_deadline = None
        game.save(update_fields=["status", "abandoned_at", "phase_deadline"])
        _invalidate_stale_invitations(game)
        release_players(game)
        _notify(game, "GAME_ABANDONED")
    logger.info("Abandon des parties bloquées : %d partie(s)", len(stuck_ids))
    return len(stuck_ids)


@transaction.atomic
def annuler_game(user, game_id: int) -> bool:
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    validate_transition(game.status, QuizGlobalGame.Status.CANCELLED)
    player = game.players.filter(player=user).first()
    if player is None:
        raise QuizGlobalError("Vous ne participez pas à cette partie.")
    if player.seat != "A":
        raise QuizGlobalError("Seul le créateur de la partie peut l'annuler.")
    invited = game.invited_player
    game.status = QuizGlobalGame.Status.CANCELLED
    game.invited_player = None
    game.save(update_fields=["status", "invited_player"])
    _liberer_mise_hote(game, motif="annulation")
    cancel_invitations(game)
    release_players(game)
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
    validate_transition(game.status, QuizGlobalGame.Status.CANCELLED)
    if game.invited_player_id != user.pk:
        raise QuizGlobalError("Aucune invitation en attente pour cette partie.")
    host = game.players.filter(seat="A").select_related("player").first()
    game.status = QuizGlobalGame.Status.CANCELLED
    game.invited_player = None
    game.save(update_fields=["status", "invited_player"])
    _liberer_mise_hote(game, motif="refus")
    cancel_invitations(game)
    release_players(game)
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
def _expirer_salon_en_attente(game_id: int) -> bool:
    """Annule uniquement ce salon s'il est WAITING et plus vieux que la limite.

    Transaction dédiée (commitée) : utilisée juste avant un join/get pour que
    l'annulation survive à l'exception levée ensuite.
    """
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        return False
    if (
        game.status == QuizGlobalGame.Status.WAITING
        and game.cree_le
        and game.cree_le < timezone.now() - timedelta(seconds=WAITING_EXPIRY_SECONDS)
    ):
        _expirer_salon(game)
        return True
    return False


def join_game(user, game_id: int, mise: Decimal | None = None) -> QuizGlobalGame:
    """Rejoindre une partie en attente.

    Protégé par transaction atomique + select_for_update pour garantir
    qu'un seul joueur obtient le slot playerB même en cas d'acceptations
    simultanées (anti-double-acceptation).

    Règles :
    - La partie doit être en status WAITING
    - playerB doit être NULL (partie pas encore complète)
    - Le joueur ne doit pas déjà participer à cette partie
    - Le joueur ne doit pas être engagé dans une autre partie active
    - Si une invitation ciblée existe, seul le joueur invité peut rejoindre
    """
    # ── Phase 1 : expiration ciblée (transaction dédiée, commitée) ──
    # Un salon WAITING trop vieux est annulé d'abord. L'erreur GameCancelledError
    # levée en phase 2 protège le join de la partie annulée, et l'annulation
    # persiste en base.
    _expirer_salon_en_attente(game_id)

    with transaction.atomic():
        game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
        if game is None:
            raise MatchNotFoundError()

        # ── Vérification de la machine d'états ──
        if game.status != QuizGlobalGame.Status.WAITING:
            if game.status in (
                QuizGlobalGame.Status.CANCELLED,
                QuizGlobalGame.Status.EXPIRED,
            ):
                raise GameCancelledError()
            raise GameFullError()

        # ── Anti-double-acceptation cross-game ──
        # Un joueur ne peut pas être dans deux parties actives simultanément.
        # Le verrou est la table ActivePlayer (OneToOne) : AUCUNE requête sur
        # l'historique (FINISHED/CANCELLED/EXPIRED/ABANDONED) n'entre en compte.
        if has_active_game(user, exclude_game_id=game.pk):
            raise PlayerAlreadyInGameError()

        # ── Idem pour l'hôte : il ne doit pas déjà jouer un autre duel ──
        # A ne peut pas créer game1→B et game2→C puis jouer les deux à la fois.
        host = game.players.filter(seat="A").select_related("player").first()
        if host is not None and has_active_game(host.player, exclude_game_id=game.pk):
            raise PlayerAlreadyInGameError(
                "L'hôte est déjà engagé dans une autre partie Quizz Global."
            )

        # ── Déjà dans cette partie ? ──
        if game.players.filter(player=user).exists():
            raise GameNotJoinableError("Vous êtes déjà dans cette partie.")

        # ── Invitation ciblée : seul le joueur invité peut rejoindre ──
        if game.invited_player_id and game.invited_player_id != user.pk:
            raise GameNotJoinableError("Cette partie est réservée à un autre joueur.")

        # ── Nombre max de joueurs (2) ──
        if game.players.count() >= 2:
            raise GameFullError()

        # ── Portefeuille requis si mise ──
        if not hasattr(user, "portefeuille"):
            raise ValidationError("Portefeuille introuvable.")

        # ── Mise : le serveur décide. L'invite ne peut pas modifier la mise de l'hôte. ──
        eff = Decimal("0")
        proposition = Decimal("0")
        if game.mise > 0:
            proposition = game.mise if mise is None else _valider_mise(mise, user.portefeuille)
        game.mise_proposee_invite = proposition

        # ── Création du playerB + réserve ActivePlayer + transition atomique ──
        QuizGlobalPlayer.objects.create(game=game, player=user, seat="B")
        reserve_player(user, game)

        # ── Invitations : celle de B est acceptée, les autres deviennent EXPIRED ──
        host_p = game.players.filter(seat="A").first()
        inv = QuizGlobalInvitation.objects.filter(game=game, receiver=user).first()
        if inv is None:
            _sync_invitation_row(game, user.pk, host_p.player if host_p else None)
            inv = QuizGlobalInvitation.objects.filter(game=game, receiver=user).first()
        if inv is not None:
            accept_invitation(inv)
        _expire_peers(game, user)

        # Appliquer la transition via la machine d'états
        validate_transition(game.status, QuizGlobalGame.Status.THEME_SELECTION)
        now = timezone.now()
        game.status = QuizGlobalGame.Status.THEME_SELECTION
        game.started_at = now
        game.phase_started_at = now
        game.phase_deadline = None
        game.active_seat = "A"
        game.save()

        # ── Gestion des mises ──
        if game.mise > 0:
            wallet_services.bloquer_mise(
                user.portefeuille,
                proposition,
                reference=_mise_reference(game.pk, user.pk),
                metadata={"game": game.pk, "role": "invite"},
                idempotency_key=f"reserve:{game.pk}:{user.pk}",
            )
            eff = min(game.mise, proposition) if proposition > 0 else game.mise
            host_player = game.players.filter(seat="A").select_related("player__portefeuille").first()
            surplus_hote = game.mise - eff
            if surplus_hote > 0 and host_player and hasattr(host_player.player, "portefeuille"):
                wallet_services.liberer_mise(
                    host_player.player.portefeuille,
                    surplus_hote,
                    reference=f"surplus-quiz-global-{game.pk}-{host_player.player.pk}",
                    metadata={"game": game.pk, "role": "hote", "type_de_surplus": "mise"},
                    idempotency_key=f"surplus:{game.pk}:{host_player.player.pk}",
                )
            surplus_invite = proposition - eff
            if surplus_invite > 0:
                wallet_services.liberer_mise(
                    user.portefeuille,
                    surplus_invite,
                    reference=f"surplus-quiz-global-{game.pk}-{user.pk}",
                    metadata={"game": game.pk, "role": "invite", "type_de_surplus": "mise"},
                    idempotency_key=f"surplus:{game.pk}:{user.pk}",
                )
            wallet_services.engager_mise(
                host_player.player.portefeuille if host_player else user.portefeuille,
                eff,
                reference=f"engage-quiz-global-{game.pk}-hote",
                metadata={"game": game.pk},
            )
            wallet_services.engager_mise(
                user.portefeuille,
                eff,
                reference=f"engage-quiz-global-{game.pk}-{user.pk}",
                metadata={"game": game.pk},
            )

        # ── Diffusion WebSocket ──
        _notify(game, "PLAYER_JOINED")
        _notify(game, "GAME_STARTED")
        _notify(game, "THEME_SELECTION_STARTED")

        # Notifier l'hôte via WebSocket de notifications
        try:
            channel_layer = get_channel_layer()
            host_player = game.players.filter(seat="A").select_related("player").first()
            if host_player:
                async_to_sync(channel_layer.group_send)(
                    f"notifications_{host_player.player_id}",
                    {
                        "type": "notify",
                        "data": {
                            "type": "quiz_global.invite_accepted",
                            "game_id": game.pk,
                            "host_id": host_player.player_id,
                            "invite_id": user.pk,
                            "invite_pseudo": user.pseudo,
                        },
                    },
                )
        except Exception as e:
            logger.error(f"Erreur diffusion notification acceptation quiz global: {e}")

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
    validate_transition(game.status, QuizGlobalGame.Status.QUESTION_READING)
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
    validate_transition(game.status, QuizGlobalGame.Status.ANSWERING)
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
    validate_transition(game.status, QuizGlobalGame.Status.QUESTION_FINISHED)
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
        validate_transition(game.status, QuizGlobalGame.Status.THEME_SELECTION)
        game.status = QuizGlobalGame.Status.THEME_SELECTION
        game.phase_started_at = timezone.now()
        game.phase_deadline = None
        game.save()
        _notify(game, "NEXT_TURN")
        _notify(game, "THEME_SELECTION_STARTED")
        return

    if score_a == score_b:
        validate_transition(game.status, QuizGlobalGame.Status.TIE_BREAK_THEME)
        game.status = QuizGlobalGame.Status.TIE_BREAK_THEME
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
    validate_transition(game.status, QuizGlobalGame.Status.FINISHED)
    game.status = QuizGlobalGame.Status.FINISHED
    game.finished_at = timezone.now()
    game.phase_deadline = None

    if game.mise > 0:
        eff = mise_effective(game)
        if not draw and winner is not None:
            loser_player = players["B"].player if winner.pk == players["A"].player_id else players["A"].player
            gagnant_pf = next((p.portefeuille for p in (players["A"].player, players["B"].player) if p.pk == winner.pk and hasattr(p, "portefeuille")), None)
            perdant_pf = next((p.portefeuille for p in (players["A"].player, players["B"].player) if p.pk == loser_player.pk and hasattr(p, "portefeuille")), None)
            if gagnant_pf and perdant_pf:
                wallet_services.GameSettlementService.regler_duel(
                    portefeuille_gagnant=gagnant_pf,
                    portefeuille_perdant=perdant_pf,
                    mise_effective=eff,
                    reference=f"quiz-global-{game.pk}",
                    metadata={"game": game.pk},
                )
        else:
            for pl in (players.get("A"), players.get("B")):
                if pl is not None and hasattr(pl.player, "portefeuille"):
                    wallet_services.liberer_mise(
                        pl.player.portefeuille,
                        eff,
                        type_=LedgerEntry.Type.REMBOURSEMENT,
                        reference=f"egalite-quiz-global-{game.pk}-{pl.player.pk}",
                        metadata={"game": game.pk},
                        idempotency_key=f"settle:{game.pk}:egalite:{pl.player.pk}",
                    )
    game.save()
    _invalidate_stale_invitations(game)
    release_players(game)
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


@transaction.atomic
def revanche_game(user, game_id: int, target_questions: int | None = None) -> QuizGlobalGame:
    """Recrée une partie immédiate contre le même adversaire après une partie terminée."""
    game = QuizGlobalGame.objects.select_for_update().filter(pk=game_id).first()
    if game is None:
        raise MatchNotFoundError()
    if game.status != QuizGlobalGame.Status.FINISHED:
        raise QuizGlobalError("Seules les parties terminées peuvent avoir une revanche.")
    # La partie d'origine étant FINISHED, ses joueurs sont libérés pour la revanche.
    release_players(game)
    players = _player_map(game)
    if user.pk not in {p.player_id for p in players.values()}:
        raise QuizGlobalError("Vous ne participez pas à cette partie.")
    opponent = next((p.player for p in players.values() if p.player_id != user.pk and p.player is not None), None)
    if opponent is None:
        raise QuizGlobalError("Aucun adversaire disponible pour une revanche.")
    if target_questions is not None and target_questions not in TARGET_ALLOWED:
        raise ValidationError("Le nombre de questions doit être 4, 8 ou 12.")
    # ── Une seule partie réellement active par joueur ──
    # La partie d'origine est FINISHED : ses joueurs ont déjà été libérés.
    # On vérifie qu'aucun des deux n'est engagé ailleurs avant de réserver.
    for p in (user, opponent):
        active = get_active_game(p, exclude_game_id=game.pk)
        if active is not None:
            raise QuizGlobalError("Un des deux joueurs a déjà une autre partie active.")
    now = timezone.now()
    new_game = QuizGlobalGame.objects.create(
        target_questions=target_questions or game.target_questions,
        mise=game.mise,
        status=QuizGlobalGame.Status.THEME_SELECTION,
        active_seat="A",
        started_at=now,
        phase_started_at=now,
    )
    QuizGlobalPlayer.objects.create(game=new_game, player=user, seat="A")
    QuizGlobalPlayer.objects.create(game=new_game, player=opponent, seat="B")
    reserve_player(user, new_game)
    reserve_player(opponent, new_game)
    if new_game.mise > 0:
        if not hasattr(user, "portefeuille"):
            raise ValidationError("Portefeuille introuvable.")
        wallet_services.bloquer_mise(
            user.portefeuille,
            new_game.mise,
            reference=_mise_reference(new_game.pk, user.pk),
            metadata={"game": new_game.pk, "role": "hote"},
            idempotency_key=f"reserve:{new_game.pk}:{user.pk}",
        )
        wallet_services.bloquer_mise(
            opponent.portefeuille,
            new_game.mise,
            reference=_mise_reference(new_game.pk, opponent.pk),
            metadata={"game": new_game.pk, "role": "invite"},
            idempotency_key=f"reserve:{new_game.pk}:{opponent.pk}",
        )
        eff = min(new_game.mise, new_game.mise) if new_game.mise > 0 else 0
        if eff > 0:
            wallet_services.engager_mise(
                user.portefeuille,
                eff,
                reference=f"engage-quiz-global-{new_game.pk}-hote",
                metadata={"game": new_game.pk},
            )
            wallet_services.engager_mise(
                opponent.portefeuille,
                eff,
                reference=f"engage-quiz-global-{new_game.pk}-invite",
                metadata={"game": new_game.pk},
            )
    _notify(new_game, "GAME_CREATED")
    _notify(new_game, "GAME_STARTED")
    _notify(new_game, "THEME_SELECTION_STARTED")
    envoyer_notification(
        opponent,
        Notification.Type.DEFI_RECU,
        "Revanche Quizz Global",
        f"{user.pseudo} vous invite à une revanche Quizz Global ({new_game.target_questions} questions).",
        reference_id=new_game.pk,
        expediteur=user,
    )
    return new_game


def list_waiting_games():
    expirer_parties_en_attente()
    return (
        QuizGlobalGame.objects.filter(status=QuizGlobalGame.Status.WAITING, invited_player__isnull=True)
        .select_related("invited_player")
        .prefetch_related("players__player")
        .order_by("-cree_le")
    )


def list_my_games(user):
    expirer_parties_en_attente()
    return (
        QuizGlobalGame.objects.filter(players__player=user)
        .exclude(status__in=INACTIVE_STATUSES)
        .select_related("invited_player")
        .prefetch_related("players__player")
        .distinct()
        .order_by("-cree_le")
    )


def mes_invitations(user):
    try:
        expirer_parties_en_attente()
    except Exception:
        logger.exception("expirer_parties_en_attente a échoué dans mes_invitations")
    pendantes = QuizGlobalInvitation.objects.filter(
        receiver=user,
        status=QuizGlobalInvitation.Status.PENDING,
    ).values_list("game_id", flat=True)
    return (
        QuizGlobalGame.objects.filter(
            status=QuizGlobalGame.Status.WAITING,
            pk__in=pendantes,
        )
        .select_related("invited_player")
        .prefetch_related("players__player")
        .distinct()
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
    # Expiration ciblée (transaction dédiée, commitée) : le salon rejoint un get
    # trop vieux est annulé puis traité comme introuvable.
    if _expirer_salon_en_attente(game_id):
        raise MatchNotFoundError()
    return game
