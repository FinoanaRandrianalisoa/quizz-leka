"""Règles métier « partie active unique » du Quizz Global 1v1.

Cf. Jeux_Qizz_Mada_amelioration_gameplay.md / architecture_quizz_global_1v1.md :
- Un joueur ne possède qu'UNE partie réellement active à la fois.
- FINISHED / CANCELLED / EXPIRED / ABANDONED ne bloquent jamais le joueur.
- Le Quizz Global est strictement 1 contre 1.
"""

import pytest
from datetime import timedelta
from django.utils import timezone

from apps.quiz_global.active_game_service import get_active_game, has_active_game
from apps.quiz_global.constants import ACTIVE_STATUSES, INACTIVE_STATUSES
from apps.quiz_global.errors import PlayerAlreadyInGameError
from apps.quiz_global.models import (
    QuizGlobalActivePlayer,
    QuizGlobalGame,
    QuizGlobalInvitation,
    QuizGlobalPlayer,
)
from apps.quiz_global.services import (
    abandonner_parties_bloquees,
    annuler_game,
    create_game,
    join_game,
    list_my_games,
)
from apps.users.models import Utilisateur


def _user(email, pseudo):
    return Utilisateur.objects.create_user(email=email, pseudo=pseudo, password="MotDePasse1!")


def _game(status="FINISHED", host=None, guest=None):
    game = QuizGlobalGame.objects.create(
        target_questions=4,
        status=status,
        phase_deadline=None,
    )
    if host is not None:
        QuizGlobalPlayer.objects.create(game=game, player=host, seat="A")
    if guest is not None:
        QuizGlobalPlayer.objects.create(game=game, player=guest, seat="B")
    return game


def test_constantes_actives_et_inactives():
    assert ACTIVE_STATUSES == {
        "WAITING",
        "THEME_SELECTION",
        "QUESTION_READING",
        "ANSWERING",
        "QUESTION_FINISHED",
        "TIE_BREAK_THEME",
    }
    assert INACTIVE_STATUSES == {
        "FINISHED",
        "CANCELLED",
        "EXPIRED",
        "ABANDONED",
    }
    assert ACTIVE_STATUSES.isdisjoint(INACTIVE_STATUSES)


@pytest.mark.django_db
def test_historique_nombreux_ne_bloque_pas_la_creation():
    """19 FINISHED + CANCELLED + EXPIRED + ABANDONED ne bloquent jamais."""
    a = _user("hist@mg.mg", "HistA")
    for status in ("FINISHED", "FINISHED", "CANCELLED", "EXPIRED", "ABANDONED"):
        _game(status=status, host=a)
    game = create_game(a, 4)
    assert game.status == QuizGlobalGame.Status.WAITING
    assert has_active_game(a)


@pytest.mark.django_db
def test_creation_avec_partie_active_est_refusee():
    a = _user("act@mg.mg", "ActA")
    create_game(a, 4)
    with pytest.raises(PlayerAlreadyInGameError):
        create_game(a, 8)


@pytest.mark.django_db
def test_waiting_bloque_la_creation():
    a = _user("wait@mg.mg", "WaitA")
    create_game(a, 4)
    with pytest.raises(PlayerAlreadyInGameError):
        create_game(a, 4)


@pytest.mark.django_db
def test_expired_libere_le_joueur():
    a = _user("expires@mg.mg", "ExpA")
    game = create_game(a, 4)
    game.status = QuizGlobalGame.Status.EXPIRED
    game.expired_at = None
    game.save()
    from apps.quiz_global.active_game_service import release_players

    release_players(game)
    assert not has_active_game(a)
    # Après EXPIRED, A peut recréer.
    game2 = create_game(a, 4)
    assert QuizGlobalActivePlayer.objects.filter(player=a).count() == 1
    assert game2.status == QuizGlobalGame.Status.WAITING


@pytest.mark.django_db
def test_abandonne_libere_les_deux_joueurs():
    a = _user("aban@mg.mg", "AbanA")
    b = _user("abanb@mg.mg", "AbanB")
    game1 = create_game(a, 4)
    game1 = join_game(b, game1.pk)
    assert QuizGlobalActivePlayer.objects.filter(player=a).exists()
    assert QuizGlobalActivePlayer.objects.filter(player=b).exists()

    # Un joueur se déconnecte : la phase reste bloquée au-delà de la grâce.
    QuizGlobalGame.objects.filter(pk=game1.pk).update(
        status=QuizGlobalGame.Status.ANSWERING,
        phase_deadline=timezone.now() - timedelta(seconds=200),
        abandoned_at=None,
    )
    assert abandonner_parties_bloquees() == 1
    game1.refresh_from_db()
    assert game1.status == QuizGlobalGame.Status.ABANDONED
    assert not has_active_game(a)
    assert not has_active_game(b)
    # Les deux peuvent immédiatement créer/rejoindre.
    create_game(a, 4)


@pytest.mark.django_db
def test_finished_a_travers_la_pipeline_libère_les_joueurs():
    """Après un vrai _finish_game (fin des questions), les joueurs sont libérés."""
    from apps.quiz_global.tests.test_quiz_global import _start_pair

    a, b, game = _start_pair(target=4)
    assert has_active_game(a) and has_active_game(b)
    # Simule la fin de partie via _finish_game : on reprend le même chemin
    # que la vraie clôture (question terminée puis tick).
    from apps.quiz_global.services import _finish_game

    game.status = QuizGlobalGame.Status.QUESTION_FINISHED
    game.save(update_fields=["status"])
    _finish_game(game, 4, 2)
    assert game.status == QuizGlobalGame.Status.FINISHED
    assert not has_active_game(a)
    assert not has_active_game(b)
    # get_active_game ne retourne plus la partie terminée.
    assert get_active_game(a) is None


@pytest.mark.django_db
def test_get_active_game_ignore_les_statuts_inactifs():
    a = _user("onlyhist@mg.mg", "OnlyHist")
    for status in ("FINISHED", "CANCELLED", "EXPIRED", "ABANDONED"):
        _game(status=status, host=a)
    assert get_active_game(a) is None
    assert not has_active_game(a)


@pytest.mark.django_db
def test_une_seule_partie_active_se_retrouve_par_get_active_game():
    a = _user("one@mg.mg", "OneA")
    _game(status="FINISHED", host=a)
    active = create_game(a, 4)
    assert get_active_game(a).pk == active.pk


@pytest.mark.django_db
def test_invitations_multiples_expirent_sauf_acceptee():
    a = _user("inv@mg.mg", "InvA")
    b = _user("invb@mg.mg", "InvB")
    c = _user("invc@mg.mg", "InvC")
    d = _user("invd@mg.mg", "InvD")
    game = create_game(a, 4, invite_id=b.pk)
    QuizGlobalInvitation.objects.create(game=game, sender=a, receiver=c)
    QuizGlobalInvitation.objects.create(game=game, sender=a, receiver=d)
    assert QuizGlobalInvitation.objects.filter(game=game, status="PENDING").count() == 3

    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION
    assert QuizGlobalInvitation.objects.filter(game=game, receiver=b).count() == 1
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "ACCEPTED"
    assert QuizGlobalInvitation.objects.filter(game=game, status="PENDING").count() == 0
    assert QuizGlobalInvitation.objects.filter(game=game, receiver=c).count() == 1
    assert QuizGlobalInvitation.objects.get(game=game, receiver=c).status == "EXPIRED"
    assert QuizGlobalInvitation.objects.get(game=game, receiver=d).status == "EXPIRED"
    # Strict 1v1 : seulement 2 joueurs, pas de C ou D.
    assert QuizGlobalPlayer.objects.filter(game=game).count() == 2


@pytest.mark.django_db
def test_annuler_libère_l_hote_et_annule_les_invitations():
    a = _user("ann@mg.mg", "AnnA")
    b = _user("annb@mg.mg", "AnnB")
    game = create_game(a, 4, invite_id=b.pk)
    assert has_active_game(a)
    annuler_game(a, game.pk)
    assert not has_active_game(a)
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "CANCELLED"
    # L'hôte annulé peut immédiatement recréer.
    create_game(a, 4)


@pytest.mark.django_db
def test_rejoindre_une_partie_active_dans_une_autre_est_refuse():
    a = _user("cross@mg.mg", "CrossA")
    b = _user("crossb@mg.mg", "CrossB")
    c = _user("crossc@mg.mg", "CrossC")
    game1 = create_game(a, 4)
    game1 = join_game(b, game1.pk)
    game2 = create_game(c, 4)
    with pytest.raises(PlayerAlreadyInGameError):
        join_game(b, game2.pk)


@pytest.mark.django_db
def test_my_active_game_n_explose_pas_avec_l_historique():
    """Le nombre de parties historiques ne doit jamais gonfler la liste active."""
    a = _user("many@mg.mg", "ManyA")
    for i in range(19):
        _game(status="FINISHED", host=a)
    for i in range(5):
        _game(status="CANCELLED", host=a)
    assert not has_active_game(a)
    active = create_game(a, 4)
    assert list(list_my_games(a)) == [active]