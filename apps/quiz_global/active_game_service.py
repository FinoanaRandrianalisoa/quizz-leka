"""Service central « partie active » — un seul joueur, une seule partie active.

Responsabilités :
- trouver la partie active d'un joueur
- réserver un joueur sur une partie (UniqueConstraint OneToOne à la base)
- libérer les joueurs d'une partie dès qu'elle devient inactive
- gérer le cycle de vie des invitations (PENDING -> ACCEPTED/EXPIRED/CANCELLED)
"""

from django.db import transaction

from apps.quiz_global.models import QuizGlobalActivePlayer, QuizGlobalGame, QuizGlobalInvitation


def get_active_game(user, exclude_game_id=None):
    """Retourne la partie réellement active du joueur (ou None)."""
    rows = QuizGlobalActivePlayer.objects.filter(player=user).select_related("game", "game__invited_player")
    if exclude_game_id is not None:
        rows = rows.exclude(game_id=exclude_game_id)
    row = rows.first()
    return row.game if row is not None else None


def has_active_game(user, exclude_game_id=None) -> bool:
    rows = QuizGlobalActivePlayer.objects.filter(player=user)
    if exclude_game_id is not None:
        rows = rows.exclude(game_id=exclude_game_id)
    return rows.exists()


@transaction.atomic
def reserve_player(user, game: QuizGlobalGame) -> QuizGlobalActivePlayer:
    """Réserve le joueur sur `game`.

    La contrainte OneToOne (primary_key) refuse au niveau base une seconde
    ligne pour le même joueur : c'est la garantie ultime du "1 seule partie
    active par joueur", même en cas de course concurrente.
    """
    row, created = QuizGlobalActivePlayer.objects.get_or_create(
        player=user,
        defaults={"game": game},
    )
    if not created:
        if row.game_id != game.pk:
            from apps.quiz_global.errors import PlayerAlreadyInGameError

            raise PlayerAlreadyInGameError()
        return row
    return row


def release_player(user) -> None:
    QuizGlobalActivePlayer.objects.filter(player=user).delete()


def release_players(game: QuizGlobalGame) -> None:
    """Libère tous les joueurs d'une partie (statut terminal)."""
    QuizGlobalActivePlayer.objects.filter(game=game).delete()


def _invalidate_invitations(game: QuizGlobalGame, status, exclude_id=None) -> int:
    qs = QuizGlobalInvitation.objects.filter(game=game, status=QuizGlobalInvitation.Status.PENDING)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.update(status=status)


def accept_invitation(invitation: QuizGlobalInvitation) -> None:
    """Un joueur accepte : marque son invitation et expirera les autres."""
    invitation.status = QuizGlobalInvitation.Status.ACCEPTED
    invitation.responded_at = None
    invitation.save(update_fields=["status", "responded_at"])
    _invalidate_invitations(invitation.game, QuizGlobalInvitation.Status.EXPIRED, exclude_id=invitation.pk)


def cancel_invitations(game: QuizGlobalGame) -> None:
    """Annulation du salon : toutes les invitations PENDING passent à CANCELLED."""
    _invalidate_invitations(game, QuizGlobalInvitation.Status.CANCELLED)


def expire_invitations(game: QuizGlobalGame) -> None:
    """Expiration du salon : toutes les invitations PENDING passent à EXPIRED."""
    _invalidate_invitations(game, QuizGlobalInvitation.Status.EXPIRED)