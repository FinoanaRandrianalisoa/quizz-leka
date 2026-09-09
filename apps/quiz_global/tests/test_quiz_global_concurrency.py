"""Tests de concurrence pour garantir le strict 1v1 du Quizz Global.

Cas couverts (cf. architecture_quizz_global_1v1.md §35) :
- Test 2 : C accepte après B  -> C refusé (GAME_FULL / MATCH_NOT_JOINABLE)
- Test 4 : ancienne invitation sur partie complète -> refus
- Test 5 : partie annulée -> refus (GAME_CANCELLED)
- Test 6 : double clic de B -> une seule association
- Cases : un joueur engagé dans une partie active ne peut pas en rejoindre/créer une autre
"""

import pytest

from apps.quiz_global.errors import (
    GameCancelledError,
    GameFullError,
    GameNotJoinableError,
    MatchNotFoundError,
    PlayerAlreadyInGameError,
)
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
    expirer_parties_en_attente,
    get_game,
    join_game,
    list_my_games,
)
from apps.users.models import Utilisateur


def _user(email, pseudo):
    return Utilisateur.objects.create_user(email=email, pseudo=pseudo, password="MotDePasse1!")


@pytest.mark.django_db
def test_second_join_after_first_wins_is_rejected():
    """Test 2 : B accepte, puis C accepte -> seule la partie A+B est valide.

    Ici la partie est réservée à B (invitation ciblée) : C est rejeté avec
    "réservée à un autre joueur" ; le nombre de joueurs reste 2.
    """
    a = _user("a@conc.mg", "Alice")
    b = _user("b@conc.mg", "Bob")
    c = _user("c@conc.mg", "Char")
    game = create_game(a, 4, invite_id=b.pk)

    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION
    assert set(game.players.values_list("seat", flat=True)) == {"A", "B"}

    # C est exclu : la partie est soit réservée à B, soit déjà complète.
    with pytest.raises(GameNotJoinableError) as exc:
        join_game(c, game.pk)
    assert exc.value.code in {"MATCH_NOT_JOINABLE", "GAME_FULL"}
    assert game.players.count() == 2


@pytest.mark.django_db
def test_invite_reserved_for_another_player():
    """Une partie avec invitation ciblée n'accepte que le joueur invité."""
    a = _user("a@conc2.mg", "Alice2")
    b = _user("b@conc2.mg", "Bob2")
    c = _user("c@conc2.mg", "Char2")
    game = create_game(a, 4, invite_id=b.pk)

    with pytest.raises(GameNotJoinableError):
        join_game(c, game.pk)

    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION


@pytest.mark.django_db
def test_double_click_same_player_rejected():
    """Test 6 : B clique deux fois rapidement -> une seule association."""
    a = _user("a@dc.mg", "AliceDC")
    b = _user("b@dc.mg", "BobDC")
    game = create_game(a, 4, invite_id=b.pk)

    join_game(b, game.pk)
    with pytest.raises(GameNotJoinableError):
        join_game(b, game.pk)
    assert QuizGlobalPlayer.objects.filter(game=game).count() == 2


@pytest.mark.django_db
def test_join_cancelled_game_rejected():
    """Test 5 : A annule, puis B accepte -> GAME_CANCELLED."""
    a = _user("a@cancel.mg", "AliceC")
    b = _user("b@cancel.mg", "BobC")
    game = create_game(a, 4, invite_id=b.pk)

    annuler_game(a, game.pk)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.CANCELLED

    with pytest.raises(GameCancelledError):
        join_game(b, game.pk)


@pytest.mark.django_db
def test_player_cannot_join_second_game_while_active():
    """Un joueur déjà dans une partie active ne peut pas rejoindre une autre partie."""
    a = _user("a@cross.mg", "AliceX")
    hub = _user("hub@cross.mg", "HubX")
    b = _user("b@cross.mg", "BobX")
    c = _user("c@cross.mg", "CharX")

    # hub crée une partie et b la rejoint -> b est maintenant actif
    game1 = create_game(hub, 4, invite_id=b.pk)
    join_game(b, game1.pk)

    # c crée une autre partie ; b tente de rejoindre game2 pendant que game1 est actif
    game2 = create_game(c, 4)
    with pytest.raises(PlayerAlreadyInGameError):
        join_game(b, game2.pk)


@pytest.mark.django_db
def test_player_cannot_create_second_game_while_active():
    """Un joueur déjà dans une partie active ne peut pas en créer une nouvelle."""
    a = _user("a@cross2.mg", "AliceY")
    b = _user("b@cross2.mg", "BobY")

    game1 = create_game(a, 4, invite_id=b.pk)
    join_game(b, game1.pk)

    with pytest.raises(PlayerAlreadyInGameError):
        create_game(b, 4)


@pytest.mark.django_db
def test_host_can_join_open_game_only_if_no_reserved_invite():
    """Cas revisité : partie ouverte (sans invitation) accepte bien un joueur libre."""
    a = _user("a@open.mg", "AliceO")
    b = _user("b@open.mg", "BobO")
    game = create_game(a, 4)

    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION
    assert set(game.players.values_list("seat", flat=True)) == {"A", "B"}


@pytest.mark.django_db
def test_host_cannot_play_two_duels_at_once():
    """L'hôte ne peut pas jouer 2 duels simultanés.

    Barrière 1 : create_game refuse de créer une 2e partie tant que l'hôte
    a déjà une partie WAITING active.
    Barrière 2 (filet de sécurité) : join_game vérifie aussi l'activité
    de l'hôte avant d'associer un playerB.
    """
    a = _user("a@multi.mg", "AliceM")
    b = _user("b@multi.mg", "BobM")
    c = _user("c@multi.mg", "CharM")

    game1 = create_game(a, 4, invite_id=b.pk)

    # A ne peut pas créer une seconde partie pendant que game1 est active.
    with pytest.raises(PlayerAlreadyInGameError):
        create_game(a, 4, invite_id=c.pk)
    assert QuizGlobalGame.objects.filter(status=QuizGlobalGame.Status.WAITING).count() == 1

    # B accepte game1 : A joue maintenant contre B.
    join_game(b, game1.pk)

    # Filet de sécurité : on force un 2e salon en base pour vérifier que
    # join_game refuse aussi côté hôte.
    game2 = QuizGlobalGame.objects.create(
        target_questions=4,
        invited_player=c,
        status=QuizGlobalGame.Status.WAITING,
    )
    from apps.quiz_global.models import QuizGlobalPlayer

    QuizGlobalPlayer.objects.create(game=game2, player=a, seat="A")
    with pytest.raises(PlayerAlreadyInGameError):
        join_game(c, game2.pk)
    assert QuizGlobalPlayer.objects.filter(game=game2).count() == 1


@pytest.mark.django_db
def test_waiting_game_expires_and_mise_is_refunded():
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.wallet.models import Portefeuille

    a = _user("exp@conc.mg", "ExpAlice")
    b = _user("expb@conc.mg", "ExpBob")
    pf_a = Portefeuille.objects.get(utilisateur=a)
    pf_a.solde_recharge = Decimal("1000")
    pf_a.save(update_fields=["solde_recharge"])
    a.portefeuille.refresh_from_db()

    game = create_game(a, 4, mise=Decimal("100"), invite_id=b.pk)
    pf_a.refresh_from_db()
    assert pf_a.solde_bloque == Decimal("100")

    # Fais vieillir le salon au-delà des 30 minutes de délai d'expiration.
    QuizGlobalGame.objects.filter(pk=game.pk).update(cree_le=timezone.now() - timedelta(minutes=31))

    assert expirer_parties_en_attente() == 1
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.EXPIRED

    # La mise bloquée est remboursée à l'hôte.
    pf_a.refresh_from_db()
    assert pf_a.solde_bloque == Decimal("0")
    assert pf_a.solde_recharge == Decimal("1000")

    # L'hôte est libéré : plus de partie active ni d'invitation visible côté invité.
    assert list(list_my_games(a)) == []
    assert not QuizGlobalActivePlayer.objects.filter(player=a).exists()
    with pytest.raises(GameCancelledError):
        join_game(b, game.pk)


@pytest.mark.django_db
def test_recent_waiting_game_is_not_expired():
    a = _user("recent@conc.mg", "RecentA")
    b = _user("recentb@conc.mg", "RecentB")
    game = create_game(a, 4, invite_id=b.pk)

    assert expirer_parties_en_attente() == 0
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.WAITING
    assert len(list(list_my_games(a))) == 1


@pytest.mark.django_db
def test_get_game_expires_old_waiting_game():
    from datetime import timedelta

    from django.utils import timezone

    a = _user("get@conc.mg", "GetA")
    b = _user("getb@conc.mg", "GetB")
    game = create_game(a, 4, invite_id=b.pk)
    QuizGlobalGame.objects.filter(pk=game.pk).update(cree_le=timezone.now() - timedelta(minutes=31))

    with pytest.raises(MatchNotFoundError):
        get_game(game.pk)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.EXPIRED
    assert list(list_my_games(a)) == []


@pytest.mark.django_db
def test_join_expired_waiting_game_is_cancelled():
    from datetime import timedelta

    from django.utils import timezone

    a = _user("join@conc.mg", "JoinA")
    b = _user("joinb@conc.mg", "JoinB")
    game = create_game(a, 4, invite_id=b.pk)
    QuizGlobalGame.objects.filter(pk=game.pk).update(cree_le=timezone.now() - timedelta(minutes=31))

    with pytest.raises(GameCancelledError):
        join_game(b, game.pk)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.EXPIRED
    assert QuizGlobalPlayer.objects.filter(game=game).count() == 1