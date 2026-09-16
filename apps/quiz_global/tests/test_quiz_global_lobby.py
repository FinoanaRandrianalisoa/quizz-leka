"""WebSocket du lobby Quizz Global.

- `build_lobby_state` : snapshot public (parties en cours, salons ouverts) +
  données personnelles (mes parties, ma partie active, invitations) ;
- `broadcast_lobby` : diffusion temps réel du bloc public au groupe du lobby.

Ces deux briques remplacent le polling GraphQL du lobby toutes les 4 secondes.
"""

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.quiz_global.services import (
    LOBBY_GROUP,
    broadcast_lobby,
    build_lobby_state,
    create_game,
    join_game,
)
from apps.users.models import Utilisateur


def _user(email, pseudo):
    return Utilisateur.objects.create_user(
        email=email, pseudo=pseudo, password="MotDePasse1!"
    )


@pytest.mark.django_db
def test_build_lobby_state_expose_parties_actives_et_donnees_personnelles():
    host = _user("lobby-host@mg.mg", "LobbyHost")
    guest = _user("lobby-guest@mg.mg", "LobbyGuest")
    other = _user("lobby-other@mg.mg", "LobbyOther")

    game = create_game(host, 4)
    game = join_game(guest, game.pk)
    assert game.status == "THEME_SELECTION"

    spectator_state = build_lobby_state(other)
    assert spectator_state["event"] == "LOBBY_STATE"
    assert spectator_state["maPartieActive"] is None
    assert spectator_state["mesParties"] == []
    assert spectator_state["invitations"] == []

    active_ids = [g["gameId"] for g in spectator_state["partiesActives"]]
    assert game.pk in active_ids
    # Vue strictement publique : jamais de contenu de question.
    active = next(
        g for g in spectator_state["partiesActives"] if g["gameId"] == game.pk
    )
    assert "question" not in active
    assert active["playerA"]["pseudo"] == "LobbyHost"
    assert active["playerB"]["pseudo"] == "LobbyGuest"

    host_state = build_lobby_state(host)
    assert host_state["maPartieActive"]["gameId"] == game.pk
    assert [g["gameId"] for g in host_state["mesParties"]] == [game.pk]


@pytest.mark.django_db
def test_broadcast_lobby_diffuse_les_parties_actives_au_groupe():
    host = _user("lobby-bcast-a@mg.mg", "BcastA")
    guest = _user("lobby-bcast-b@mg.mg", "BcastB")

    game = create_game(host, 4)
    game = join_game(guest, game.pk)

    layer = get_channel_layer()
    channel = "test-lobby-channel"
    async_to_sync(layer.group_add)(LOBBY_GROUP, channel)
    try:
        broadcast_lobby()
        message = async_to_sync(layer.receive)(channel)
    finally:
        async_to_sync(layer.group_discard)(LOBBY_GROUP, channel)

    assert message is not None
    data = message["data"]
    assert data["event"] == "LOBBY_UPDATED"
    active_ids = [g["gameId"] for g in data["partiesActives"]]
    assert game.pk in active_ids
    # Aucune question exposée dans le bloc public du lobby.
    assert all("question" not in g for g in data["partiesActives"])
