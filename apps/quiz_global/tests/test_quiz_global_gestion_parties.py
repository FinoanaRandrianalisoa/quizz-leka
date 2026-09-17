"""Gestion des parties : annulation/abandon, invitations multiples, historique.

Fonctionnalités ajoutées au Quizz Global :
- Le créateur peut annuler un salon WAITING (CANCELLED) ;
- Un participant peut clore une partie démarrée (ABANDONED) : le serveur rembourse
  les mises engagées et libère les deux joueurs (plus de partie "fantôme" bloquante) ;
- Plusieurs invitations PENDING sont possibles sur un même salon (premier acceptant
  = place B, les autres expirent) ;
- L'historique expose toutes les parties (actives + terminées).
"""

import pytest
from decimal import Decimal

from apps.quiz_global.active_game_service import get_active_game, has_active_game
from apps.quiz_global.errors import (
    GameNotJoinableError,
    QuizGlobalError,
)
from apps.quiz_global.models import (
    QuizGlobalActivePlayer,
    QuizGlobalGame,
    QuizGlobalInvitation,
    QuizGlobalPlayer,
)
from apps.quiz_global.services import (
    annuler_game,
    annuler_invitation,
    create_game,
    inviter_joueur,
    join_game,
    list_my_games_history,
    refuser_invitation,
)
from apps.users.models import Utilisateur


def _user(email, pseudo):
    return Utilisateur.objects.create_user(email=email, pseudo=pseudo, password="MotDePasse1!")


@pytest.mark.django_db
def test_hote_peut_annuler_salon_waiting():
    from apps.wallet.models import Portefeuille

    a = _user("mi@mg.mg", "MiseA")
    b = _user("mib@mg.mg", "MiseB")
    pf_a = Portefeuille.objects.get(utilisateur=a)
    pf_a.solde_recharge = Decimal("1000")
    pf_a.save(update_fields=["solde_recharge"])
    a.portefeuille.refresh_from_db()

    game = create_game(a, 4, mise=Decimal("50"), invite_id=b.pk)
    assert game.status == QuizGlobalGame.Status.WAITING
    assert has_active_game(a)

    assert annuler_game(a, game.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.CANCELLED
    assert not has_active_game(a)
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "CANCELLED"
    # La mise réservée est remboursée.
    pf_a.refresh_from_db()
    assert pf_a.solde_bloque == Decimal("0")
    assert pf_a.solde_recharge == Decimal("1000")
    # L'hôte libéré peut immédiatement recréer.
    create_game(a, 8)


@pytest.mark.django_db
def test_invite_ne_peut_pas_annuler_un_salon_waiting():
    a = _user("waita@mg.mg", "WaitHost")
    b = _user("waitb@mg.mg", "WaitInvite")
    game = create_game(a, 4, invite_id=b.pk)
    with pytest.raises(QuizGlobalError):
        annuler_game(b, game.pk)
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.WAITING


@pytest.mark.django_db
def test_hote_peut_clore_une_partie_en_cours_et_se_debloquer():
    """Partie #59 type « THEME_SELECTION » bloquante : le créateur peut la clore."""
    a = _user("bloa@mg.mg", "BlocHost")
    b = _user("blob@mg.mg", "BlocGuest")
    game = create_game(a, 4)
    game = join_game(b, game.pk)
    assert game.status == QuizGlobalGame.Status.THEME_SELECTION
    assert has_active_game(a) and has_active_game(b)

    assert annuler_game(a, game.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.ABANDONED
    assert not has_active_game(a)
    assert not has_active_game(b)
    # A peut de nouveau créer une partie.
    create_game(a, 4)


@pytest.mark.django_db
def test_invite_peut_abandonner_une_partie_en_cours():
    """Le joueur B bloqué dans une partie démarrée peut s'en libérer (ABANDONED)."""
    a = _user("abanh@mg.mg", "AbanHost")
    b = _user("abang@mg.mg", "AbanGuest")
    game = create_game(a, 4)
    game = join_game(b, game.pk)
    assert game.status == QuizGlobalGame.Status.THEME_SELECTION

    assert annuler_game(b, game.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.ABANDONED
    assert not has_active_game(a)
    assert not has_active_game(b)


@pytest.mark.django_db
def test_abandon_rembourse_les_mises_engagees():
    from apps.wallet.models import Portefeuille

    a = _user("mf@mg.mg", "MoneyA")
    b = _user("mf2@mg.mg", "MoneyB")
    pf_a = Portefeuille.objects.get(utilisateur=a)
    pf_b = Portefeuille.objects.get(utilisateur=b)
    for pf in (pf_a, pf_b):
        pf.solde_recharge = Decimal("1000")
        pf.save(update_fields=["solde_recharge"])
    a.portefeuille.refresh_from_db()
    b.portefeuille.refresh_from_db()

    game = create_game(a, 4, mise=Decimal("100"))
    game = join_game(b, game.pk, mise=Decimal("100"))
    pf_a.refresh_from_db()
    pf_b.refresh_from_db()
    assert pf_a.solde_bloque == Decimal("100")
    assert pf_b.solde_bloque == Decimal("100")

    annuler_game(b, game.pk)
    pf_a.refresh_from_db()
    pf_b.refresh_from_db()
    assert pf_a.solde_bloque == Decimal("0")
    assert pf_b.solde_bloque == Decimal("0")
    assert pf_a.solde_recharge == Decimal("1000")
    assert pf_b.solde_recharge == Decimal("1000")


@pytest.mark.django_db
def test_invitations_multiples_un_seul_salon():
    """Envoyer l'invitation à plusieurs joueurs pour le même salon."""
    a = _user("ma@mg.mg", "MultiA")
    b = _user("mb@mg.mg", "MultiB")
    c = _user("mc@mg.mg", "MultiC")
    d = _user("md@mg.mg", "MultiD")

    game = create_game(a, 4)  # salon ouvert
    inviter_joueur(a, game.pk, b.pk)
    inviter_joueur(a, game.pk, c.pk)
    inviter_joueur(a, game.pk, d.pk)

    assert QuizGlobalInvitation.objects.filter(game=game, status="PENDING").count() == 3
    assert set(
        QuizGlobalInvitation.objects.filter(game=game, status="PENDING").values_list("receiver_id", flat=True)
    ) == {b.pk, c.pk, d.pk}

    # B accepte : C et D sont expirés (strict 1v1, B obtient la place B).
    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "ACCEPTED"
    assert QuizGlobalInvitation.objects.filter(game=game, status="PENDING").count() == 0
    for receiver in (c, d):
        assert QuizGlobalInvitation.objects.get(game=game, receiver=receiver).status == "EXPIRED"
    # C ne peut plus rejoindre : la partie est déjà engagée/pleine.
    with pytest.raises(GameNotJoinableError):
        join_game(c, game.pk)


@pytest.mark.django_db
def test_inviter_double_est_idempotent():
    a = _user("ida@mg.mg", "IdemA")
    b = _user("idb@mg.mg", "IdemB")
    game = create_game(a, 4)
    inviter_joueur(a, game.pk, b.pk)
    inviter_joueur(a, game.pk, b.pk)
    assert QuizGlobalInvitation.objects.filter(game=game, receiver=b).count() == 1
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "PENDING"


@pytest.mark.django_db
def test_annuler_une_invitation_garde_le_salon_ouvert():
    """Annuler une invitation ciblée ne ferme pas le salon (les autres restent)."""
    a = _user("cia@mg.mg", "CibleA")
    b = _user("cib@mg.mg", "CibleB")
    c = _user("cic@mg.mg", "CibleC")
    game = create_game(a, 4)
    inviter_joueur(a, game.pk, b.pk)
    inviter_joueur(a, game.pk, c.pk)
    game.refresh_from_db()
    # `invited_player` reste la plus ancienne invitation encore en attente.
    assert game.invited_player_id == b.pk

    assert annuler_invitation(a, game.pk, c.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.WAITING
    assert QuizGlobalInvitation.objects.get(game=game, receiver=c).status == "CANCELLED"
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "PENDING"
    # `invited_player` a été réaligné sur l'invitation encore valide.
    assert game.invited_player_id == b.pk

    # B peut encore rejoindre, et le salon n'est pas devenu public.
    joined = join_game(b, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION


@pytest.mark.django_db
def test_refus_invitation_conserve_le_salon_si_autres_invites():
    a = _user("rfa@mg.mg", "RefusA")
    b = _user("rfb@mg.mg", "RefusB")
    c = _user("rfc@mg.mg", "RefusC")
    game = create_game(a, 4, invite_id=b.pk)
    inviter_joueur(a, game.pk, c.pk)

    assert refuser_invitation(b, game.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.WAITING
    assert QuizGlobalInvitation.objects.get(game=game, receiver=b).status == "CANCELLED"
    assert QuizGlobalInvitation.objects.get(game=game, receiver=c).status == "PENDING"
    assert game.invited_player_id == c.pk

    joined = join_game(c, game.pk)
    assert joined.status == QuizGlobalGame.Status.THEME_SELECTION


@pytest.mark.django_db
def test_refus_derniere_invitation_annule_le_salon():
    a = _user("rla@mg.mg", "LastA")
    b = _user("rlb@mg.mg", "LastB")
    game = create_game(a, 4, invite_id=b.pk)

    assert refuser_invitation(b, game.pk) is True
    game.refresh_from_db()
    assert game.status == QuizGlobalGame.Status.CANCELLED
    assert game.invited_player_id is None


@pytest.mark.django_db
def test_annuler_invitation_reservee_au_createur():
    a = _user("pca@mg.mg", "PropA")
    b = _user("pcb@mg.mg", "PropB")
    c = _user("pcc@mg.mg", "PropC")
    game = create_game(a, 4, invite_id=b.pk)
    with pytest.raises(QuizGlobalError):
        annuler_invitation(c, game.pk, b.pk)


@pytest.mark.django_db
def test_seul_le_createur_peut_inviter():
    a = _user("invh@mg.mg", "InvHost")
    b = _user("invb@mg.mg", "InvB")
    c = _user("invc@mg.mg", "InvC")
    game = create_game(a, 4, invite_id=b.pk)
    with pytest.raises(QuizGlobalError):
        inviter_joueur(b, game.pk, c.pk)


@pytest.mark.django_db
def test_historique_contient_toutes_les_parties():
    a = _user("histh@mg.mg", "HistHost")
    b = _user("histg@mg.mg", "HistGuest")

    # Partie terminée puis annulée d'abord (A doit être libre ensuite).
    termine = create_game(a, 4)
    termine = join_game(b, termine.pk)
    from apps.quiz_global.services import _finish_game

    termine.status = QuizGlobalGame.Status.QUESTION_FINISHED
    termine.save(update_fields=["status"])
    _finish_game(termine, 4, 2)
    assert get_active_game(a) is None

    annule = create_game(a, 4)
    annuler_game(a, annule.pk)
    assert get_active_game(a) is None

    # Dernière en date : la partie réellement active.
    actif = create_game(a, 4)
    actif = join_game(b, actif.pk)

    all_games = list(list_my_games_history(a))
    assert {g.pk for g in all_games} == {actif.pk, termine.pk, annule.pk}
    # ActivePlayer uniquement sur la partie réellement active.
    assert get_active_game(a).pk == actif.pk
    statuses = {g.status for g in all_games}
    assert {QuizGlobalGame.Status.THEME_SELECTION, QuizGlobalGame.Status.FINISHED, QuizGlobalGame.Status.CANCELLED} <= statuses


@pytest.mark.django_db
def test_annuler_partie_terminee_refuse():
    a = _user("endh@mg.mg", "EndHost")
    b = _user("endg@mg.mg", "EndGuest")
    game = create_game(a, 4)
    game = join_game(b, game.pk)
    from apps.quiz_global.services import _finish_game

    game.status = QuizGlobalGame.Status.QUESTION_FINISHED
    game.save(update_fields=["status"])
    _finish_game(game, 2, 1)
    assert game.status == QuizGlobalGame.Status.FINISHED
    with pytest.raises(QuizGlobalError):
        annuler_game(a, game.pk)


@pytest.mark.django_db
def test_graphql_inviter_et_historique(client):
    import json

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

    tok_a = register("invga@quiz.mg", "InvGala")
    tok_b = register("invgb@quiz.mg", "InvGalB")
    tok_c = register("invgc@quiz.mg", "InvGalC")

    created = gql("mutation { creerPartieQuizGlobal(targetQuestions: 4) { gameId status } }", tok_a)
    assert "errors" not in created, created
    game_id = created["data"]["creerPartieQuizGlobal"]["gameId"]

    inv_b = gql(f"mutation {{ inviterPartieQuizGlobal(gameId: {game_id}, inviteId: {__import__('apps.users.models', fromlist=['Utilisateur']).Utilisateur.objects.get(email='invgb@quiz.mg').pk}) {{ gameId status }} }}", tok_a)
    assert "errors" not in inv_b, inv_b

    joined = gql(f"mutation {{ rejoindrePartieQuizGlobal(gameId: {game_id}) {{ status }} }}", tok_b)
    assert joined["data"]["rejoindrePartieQuizGlobal"]["status"] == "THEME_SELECTION"

    hist = gql("{ historiquePartiesQuizGlobal { gameId status targetQuestions } }", tok_a)
    assert "errors" not in hist, hist
    assert len(hist["data"]["historiquePartiesQuizGlobal"]) == 1
    assert hist["data"]["historiquePartiesQuizGlobal"][0]["gameId"] == game_id


@pytest.mark.django_db
def test_graphql_parties_actives_publiques(client):
    """partiesQuizGlobalActives liste les parties démarrées de tous les joueurs,
    sans exposer la question ni les options (vue spectateur)."""
    import json

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

    tok_a = register("actg@quiz.mg", "ActAla")
    tok_b = register("acth@quiz.mg", "ActBla")
    tok_c = register("acti@quiz.mg", "ActCid")

    # Salon WAITING (pas encore démarré) : ne doit PAS apparaître.
    waiting = gql("mutation { creerPartieQuizGlobal(targetQuestions: 4) { gameId status } }", tok_a)
    assert "errors" not in waiting, waiting

    # Partie démarrée entre A et B.
    started = gql(
        f"mutation {{ inviterPartieQuizGlobal(gameId: {waiting['data']['creerPartieQuizGlobal']['gameId']}, inviteId: {Utilisateur.objects.get(email='acth@quiz.mg').pk}) {{ gameId }}}}",
        tok_a,
    )
    assert "errors" not in started, started
    joined = gql(
        f"mutation {{ rejoindrePartieQuizGlobal(gameId: {waiting['data']['creerPartieQuizGlobal']['gameId']}) {{ status }} }}",
        tok_b,
    )
    assert joined["data"]["rejoindrePartieQuizGlobal"]["status"] == "THEME_SELECTION"

    # Un joueur tiers (C) voit la partie active : résumé public sans question.
    actives = gql(
        """{ partiesQuizGlobalActives { gameId status currentTurn targetQuestions playerA { pseudo score } playerB { pseudo score } } }""",
        tok_c,
    )
    assert "errors" not in actives, actives
    data = actives["data"]["partiesQuizGlobalActives"]
    assert len(data) == 1
    assert data[0]["status"] == "THEME_SELECTION"
    assert {p["pseudo"] for p in (data[0]["playerA"], data[0]["playerB"])} == {"ActAla", "ActBla"}
    assert "question" not in data[0]
    assert set(data[0]) == {
        "gameId",
        "status",
        "currentTurn",
        "targetQuestions",
        "playerA",
        "playerB",
    }