import json

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from apps.matches.models import Match, Tour, Participation
from apps.social.models import Notification
from apps.themes.models import Theme


@pytest.fixture(autouse=True)
def donnees():
    from apps.matches import services as match_services

    cache.clear()
    match_services.RPS_CHALLENGES.clear()
    match_services.RPS_MATCHES.clear()
    call_command("seed_questions", verbosity=0)
    yield
    cache.clear()
    match_services.RPS_CHALLENGES.clear()
    match_services.RPS_MATCHES.clear()


def _gql(client, query, token=None):
    kwargs = {"content_type": "application/json"}
    if token:
        kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    r = client.post("/graphql/", data={"query": query}, **kwargs)
    return json.loads(r.content)


def _register(client, email, pseudo):
    resp = _gql(
        client,
        f'mutation {{ register(input: {{ email: "{email}", pseudo: "{pseudo}", password: "MotDePasse1!" }}) {{ accessToken }} }}',
    )
    assert "errors" not in resp, resp
    return resp["data"]["register"]["accessToken"]


@pytest.mark.django_db
def test_deroulement_complet_match(client):
    tok_a = _register(client, "hote@example.mg", "Hote")
    tok_b = _register(client, "invite@example.mg", "Invite")

    theme = Theme.objects.first()
    creer = _gql(client, f'mutation {{ creerPartie(themeId: {theme.pk}, mise: "0", scoreCible: 2) {{ id statut }} }}', tok_a)
    assert creer["data"]["creerPartie"]["statut"] == "en_attente"
    match_id = creer["data"]["creerPartie"]["id"]

    detail_attente = _gql(client, f"{{ matchParId(matchId: {match_id}) {{ statut tourEnCours {{ id }} }} }}")
    assert detail_attente["data"]["matchParId"]["tourEnCours"] is None

    rejoindre = _gql(client, f'mutation {{ rejoindrePartie(matchId: {match_id}) {{ statut }} }}', tok_b)
    assert rejoindre["data"]["rejoindrePartie"]["statut"] == "en_cours"

    tour = Tour.objects.get(match_id=match_id)
    bonne = tour.question.reponses.get(est_correcte=True)
    rep = _gql(client, f'mutation {{ soumettreReponse(tourId: {tour.pk}, reponseId: {bonne.pk}) }}', tok_a)
    assert "errors" not in rep, rep

    assert Match.objects.get(pk=match_id).score_hote == 1
    assert Participation.objects.filter(match_id=match_id).count() == 2


@pytest.mark.django_db
def test_intrus_reponse_faux_met_fin_au_match(client):
    _register(client, "hote2@example.mg", "HoteB")
    tok_b = _register(client, "invite2@example.mg", "InviteB")

    theme = Theme.objects.first()
    creer = _gql(client, f'mutation {{ creerPartie(themeId: {theme.pk}, typeJeu: "intrus") {{ id }} }}', tok_b)
    match_id = creer["data"]["creerPartie"]["id"]

    _gql(client, f'mutation {{ rejoindrePartie(matchId: {match_id}) {{ statut }} }}', _register(client, "hote3@example.mg", "HoteC"))
    tour = Tour.objects.get(match_id=match_id)
    mauvaise = tour.question.reponses.filter(est_correcte=False).first()

    rep = _gql(client, f'mutation {{ soumettreReponse(tourId: {tour.pk}, reponseId: {mauvaise.pk}) }}', tok_b)
    assert "errors" not in rep, rep

    match = Match.objects.get(pk=match_id)
    assert match.statut == Match.Statut.TERMINE
    assert match.vainqueur is not None and match.vainqueur.email == "hote3@example.mg"


@pytest.mark.django_db
def test_defi_rps_cree_une_partie_ephemere(client):
    tok_a = _register(client, "rps_a@example.mg", "RpsA")
    tok_b = _register(client, "rps_b@example.mg", "RpsB")

    challenger = _gql(client, 'query { moi { id pseudo } }', tok_a)
    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)

    challenger_id = challenger["data"]["moi"]["id"]
    challenged_id = challenged["data"]["moi"]["id"]

    challenge = _gql(client, f'mutation {{ defierJoueurRps(inviteId: {challenged_id}) {{ id fromId toId }} }}', tok_a)
    assert "errors" not in challenge, challenge
    assert challenge["data"]["defierJoueurRps"]["fromId"] == challenger_id

    accepted = _gql(client, f'mutation {{ accepterDefiRps(challengeId: "{challenge["data"]["defierJoueurRps"]["id"]}") {{ id joueurHoteId joueurInviteId statut }} }}', tok_b)
    assert "errors" not in accepted, accepted
    assert accepted["data"]["accepterDefiRps"]["statut"] == "en_cours"


@pytest.mark.django_db
def test_defi_rps_affiche_les_parties_actives_pour_le_joueur(client):
    tok_a = _register(client, "rps_active_a@example.mg", "RpsActiveA")
    tok_b = _register(client, "rps_active_b@example.mg", "RpsActiveB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}) {{ id fromId toId fromPseudo toPseudo }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    accepted = _gql(
        client,
        f'mutation {{ accepterDefiRps(challengeId: "{challenge["data"]["defierJoueurRps"]["id"]}") {{ id joueurHoteId joueurInviteId statut }} }}',
        tok_b,
    )
    assert "errors" not in accepted, accepted

    active = _gql(client, 'query { mesMatchsRps { id joueurHoteId joueurInviteId statut } }', tok_a)
    assert "errors" not in active, active
    assert active["data"]["mesMatchsRps"][0]["id"] == accepted["data"]["accepterDefiRps"]["id"]
    assert active["data"]["mesMatchsRps"][0]["joueurInviteId"] == str(challenged["data"]["moi"]["id"])


@pytest.mark.django_db
def test_course_lapin_cree_une_partie_publique_et_peut_etre_rejointe(client):
    tok_hote = _register(client, "rabbit_host@example.mg", "LapinHost")
    tok_invite = _register(client, "rabbit_guest@example.mg", "LapinGuest")

    theme = Theme.objects.filter(slug="course-lapin").first()
    if theme is None:
        theme = Theme.objects.create(nom="Course lapin", slug="course-lapin", description="Course lapin", category="course lapin")

    created = _gql(
        client,
        f'mutation {{ creerPartie(themeId: {theme.pk}, scoreCible: 3, typeJeu: "course_lapin") {{ id typeJeu statut joueurHote {{ id }} joueurInvite {{ id }} }} }}',
        tok_hote,
    )
    assert "errors" not in created, created
    match_id = created["data"]["creerPartie"]["id"]
    assert created["data"]["creerPartie"]["typeJeu"] == "course_lapin"
    assert created["data"]["creerPartie"]["statut"] == "en_attente"

    joined = _gql(client, f'mutation {{ rejoindrePartie(matchId: {match_id}) {{ id statut typeJeu }} }}', tok_invite)
    assert "errors" not in joined, joined
    assert joined["data"]["rejoindrePartie"]["statut"] == "en_cours"
    assert joined["data"]["rejoindrePartie"]["typeJeu"] == "course_lapin"


@pytest.mark.django_db
def test_course_lapin_invitation_envoie_notification_et_accepte(client):
    tok_hote = _register(client, "rabbit_invite_host@example.mg", "LapinHostInvite")
    tok_invite = _register(client, "rabbit_invite_guest@example.mg", "LapinGuestInvite")
    host = _gql(client, "query { moi { id pseudo } }", tok_hote)
    invite = _gql(client, "query { moi { id pseudo } }", tok_invite)

    theme = Theme.objects.filter(slug="course-lapin").first()
    if theme is None:
        theme = Theme.objects.create(nom="Course lapin", slug="course-lapin", description="Course lapin", category="course lapin")

    created = _gql(
        client,
        f'mutation {{ creerPartie(themeId: {theme.pk}, scoreCible: 3, typeJeu: "course_lapin") {{ id typeJeu statut }} }}',
        tok_hote,
    )
    match_id = created["data"]["creerPartie"]["id"]

    invited = _gql(
        client,
        f'mutation {{ inviterJoueurCourseLapin(matchId: {match_id}, inviteId: {invite["data"]["moi"]["id"]}) {{ id statut }} }}',
        tok_hote,
    )
    assert "errors" not in invited, invited
    assert invited["data"]["inviterJoueurCourseLapin"]["statut"] == "en_attente"
    assert Notification.objects.filter(
        destinataire__pk=invite["data"]["moi"]["id"],
        type=Notification.Type.DEFI_RECU,
        reference_id=match_id,
    ).exists()

    accepted = _gql(
        client,
        f'mutation {{ accepterInvitationCourseLapin(matchId: {match_id}) {{ id statut inviteAccepte joueurInvite {{ id pseudo }} }} }}',
        tok_invite,
    )
    assert "errors" not in accepted, accepted
    assert accepted["data"]["accepterInvitationCourseLapin"]["statut"] == "en_attente"
    assert accepted["data"]["accepterInvitationCourseLapin"]["inviteAccepte"] is True
    assert accepted["data"]["accepterInvitationCourseLapin"]["joueurInvite"]["id"] == invite["data"]["moi"]["id"]
    assert Notification.objects.filter(
        destinataire__pk=host["data"]["moi"]["id"],
        type=Notification.Type.DEFI_ACCEPTE,
        titre="Tous les joueurs sont prêts",
        reference_id=match_id,
    ).exists()

    launched = _gql(
        client,
        f'mutation {{ lancerCourseLapin(matchId: {match_id}) {{ id statut }} }}',
        tok_hote,
    )
    assert "errors" not in launched, launched
    assert launched["data"]["lancerCourseLapin"]["statut"] == "en_cours"


@pytest.mark.django_db
def test_course_lapin_invitation_peut_etre_refusee(client):
    tok_hote = _register(client, "rabbit_refuse_host@example.mg", "LapinHostRefuse")
    tok_invite = _register(client, "rabbit_refuse_guest@example.mg", "LapinGuestRefuse")
    invite = _gql(client, "query { moi { id pseudo } }", tok_invite)

    theme = Theme.objects.filter(slug="course-lapin").first()
    if theme is None:
        theme = Theme.objects.create(nom="Course lapin", slug="course-lapin", description="Course lapin", category="course lapin")

    created = _gql(
        client,
        f'mutation {{ creerPartie(themeId: {theme.pk}, scoreCible: 3, typeJeu: "course_lapin") {{ id }} }}',
        tok_hote,
    )
    match_id = created["data"]["creerPartie"]["id"]
    _gql(
        client,
        f'mutation {{ inviterJoueurCourseLapin(matchId: {match_id}, inviteId: {invite["data"]["moi"]["id"]}) {{ id }} }}',
        tok_hote,
    )
    refused = _gql(
        client,
        f'mutation {{ refuserInvitationCourseLapin(matchId: {match_id}) {{ id joueurInvite {{ id }} inviteAccepte }} }}',
        tok_invite,
    )
    assert "errors" not in refused, refused
    assert refused["data"]["refuserInvitationCourseLapin"]["joueurInvite"] is None
    assert refused["data"]["refuserInvitationCourseLapin"]["inviteAccepte"] is False


@pytest.mark.django_db
def test_defi_rps_peut_choisir_un_score_cible_personnalise(client):
    tok_a = _register(client, "rps_custom_a@example.mg", "RpsCustomA")
    tok_b = _register(client, "rps_custom_b@example.mg", "RpsCustomB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}, scoreCible: 5) {{ id scoreCible }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge
    assert challenge["data"]["defierJoueurRps"]["scoreCible"] == 5

    accepted = _gql(
        client,
        f'mutation {{ accepterDefiRps(challengeId: "{challenge["data"]["defierJoueurRps"]["id"]}") {{ id scoreCible statut }} }}',
        tok_b,
    )
    assert "errors" not in accepted, accepted
    assert accepted["data"]["accepterDefiRps"]["scoreCible"] == 5


@pytest.mark.django_db
def test_defi_rps_egalite_ne_ajoute_pas_de_point_et_avance_la_manche(client):
    tok_a = _register(client, "rps_tie_a@example.mg", "RpsTieA")
    tok_b = _register(client, "rps_tie_b@example.mg", "RpsTieB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}) {{ id }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    accepted = _gql(
        client,
        f'mutation {{ accepterDefiRps(challengeId: "{challenge["data"]["defierJoueurRps"]["id"]}") {{ id }} }}',
        tok_b,
    )
    match_id = accepted["data"]["accepterDefiRps"]["id"]

    first = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "pierre") {{ scoreHote scoreInvite round statut resultatManche }} }}', tok_a)
    second = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "pierre") {{ scoreHote scoreInvite round statut resultatManche }} }}', tok_b)

    assert "errors" not in first, first
    assert "errors" not in second, second
    assert first["data"]["jouerCoupRps"]["scoreHote"] == 0
    assert second["data"]["jouerCoupRps"]["scoreInvite"] == 0
    assert second["data"]["jouerCoupRps"]["round"] == 2
    assert second["data"]["jouerCoupRps"]["statut"] == "en_cours"


@pytest.mark.django_db
def test_defi_rps_retourne_resultat_de_manche_et_avance_jusqua_score_final(client):
    tok_a = _register(client, "rps_result_a@example.mg", "RpsResultA")
    tok_b = _register(client, "rps_result_b@example.mg", "RpsResultB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}, scoreCible: 2) {{ id }} }}',
        tok_a,
    )
    accepted = _gql(
        client,
        f'mutation {{ accepterDefiRps(challengeId: "{challenge["data"]["defierJoueurRps"]["id"]}") {{ id }} }}',
        tok_b,
    )
    match_id = accepted["data"]["accepterDefiRps"]["id"]

    first = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "pierre") {{ scoreHote scoreInvite round resultatManche statut }} }}', tok_a)
    second = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "ciseaux") {{ scoreHote scoreInvite round resultatManche statut }} }}', tok_b)

    assert "errors" not in first, first
    assert "errors" not in second, second
    assert second["data"]["jouerCoupRps"]["scoreHote"] == 1
    assert second["data"]["jouerCoupRps"]["scoreInvite"] == 0
    assert second["data"]["jouerCoupRps"]["round"] == 2
    assert "resultatManche" in second["data"]["jouerCoupRps"]
    assert second["data"]["jouerCoupRps"]["resultatManche"]

    third = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "papier") {{ scoreHote scoreInvite round resultatManche statut }} }}', tok_a)
    fourth = _gql(client, f'mutation {{ jouerCoupRps(matchId: "{match_id}", coup: "pierre") {{ scoreHote scoreInvite round resultatManche statut }} }}', tok_b)

    assert third["data"]["jouerCoupRps"]["scoreHote"] == 1
    assert fourth["data"]["jouerCoupRps"]["scoreHote"] == 2
    assert fourth["data"]["jouerCoupRps"]["scoreInvite"] == 0
    assert fourth["data"]["jouerCoupRps"]["round"] == 3
    assert fourth["data"]["jouerCoupRps"]["statut"] == "termine"


@pytest.mark.django_db
def test_defi_penalty_cree_une_notification_avec_reference_chaine(client):
    tok_a = _register(client, "penalty_notif_a@example.mg", "PenaltyNotifA")
    tok_b = _register(client, "penalty_notif_b@example.mg", "PenaltyNotifB")

    challenger = _gql(client, 'query { moi { id pseudo } }', tok_a)
    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)

    challenge = _gql(
        client,
        f'mutation {{ defierJoueurPenalty(data: {{ inviteId: "{challenged["data"]["moi"]["id"]}", scoreCible: 5 }}) {{ id hoteId inviteId invitePseudo }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    notif = Notification.objects.filter(
        destinataire_id=challenged["data"]["moi"]["id"],
        type=Notification.Type.DEFI_RECU,
        message__icontains="tir au but",
    ).latest("id")
    assert notif.reference_id == 0
    assert challenge["data"]["defierJoueurPenalty"]["hoteId"] == str(challenger["data"]["moi"]["id"])


@pytest.mark.django_db
def test_defi_rps_cree_une_notification_pour_le_cible(client):
    tok_a = _register(client, "rps_notif_a@example.mg", "RpsNotifA")
    tok_b = _register(client, "rps_notif_b@example.mg", "RpsNotifB")

    challenger = _gql(client, 'query { moi { id pseudo } }', tok_a)
    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)

    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}) {{ id fromId toId }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    notif = Notification.objects.filter(
        destinataire_id=challenged["data"]["moi"]["id"],
        type=Notification.Type.DEFI_RECU,
        message__icontains="défié",
    ).first()
    assert notif is not None, "Le joueur ciblé n'a pas reçu de notification de défi."
    assert notif.reference_id == 0
    assert challenge["data"]["defierJoueurRps"]["fromId"] == challenger["data"]["moi"]["id"]


@pytest.mark.django_db
def test_defi_rps_est_visible_dans_liste_des_defis_du_cible(client):
    tok_a = _register(client, "rps_list_a@example.mg", "RpsListA")
    tok_b = _register(client, "rps_list_b@example.mg", "RpsListB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}) {{ id fromId toId fromPseudo toPseudo }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    pending = _gql(client, 'query { mesDefisRps { id fromId fromPseudo toId toPseudo } }', tok_b)
    assert "errors" not in pending, pending
    assert pending["data"]["mesDefisRps"][0]["id"] == challenge["data"]["defierJoueurRps"]["id"]
    assert pending["data"]["mesDefisRps"][0]["fromPseudo"] == "RpsListA"


@pytest.mark.django_db
def test_defi_rps_persiste_dans_le_cache_redis(client):
    tok_a = _register(client, "rps_cache_a@example.mg", "RpsCacheA")
    tok_b = _register(client, "rps_cache_b@example.mg", "RpsCacheB")

    challenged = _gql(client, 'query { moi { id pseudo } }', tok_b)
    challenge = _gql(
        client,
        f'mutation {{ defierJoueurRps(inviteId: {challenged["data"]["moi"]["id"]}) {{ id fromId toId fromPseudo toPseudo }} }}',
        tok_a,
    )
    assert "errors" not in challenge, challenge

    challenge_id = challenge["data"]["defierJoueurRps"]["id"]
    stored = cache.get(f"rps:challenge:{challenge_id}")
    assert stored is not None
    assert stored["to_id"] == int(challenged["data"]["moi"]["id"])
    assert challenge_id in (cache.get("rps:challenge:index") or [])


@pytest.mark.django_db
def test_defi_rps_fallback_memoire_si_redis_absent(monkeypatch):
    from apps.matches import services

    class BrokenCache:
        def get(self, *args, **kwargs):
            raise ConnectionError("Redis absent")

        def set(self, *args, **kwargs):
            raise ConnectionError("Redis absent")

        def delete(self, *args, **kwargs):
            raise ConnectionError("Redis absent")

    monkeypatch.setattr(services, "cache", BrokenCache())
    store = services.RpsStateStore("fallback")
    store["abc"] = {"id": "abc"}

    assert store["abc"]["id"] == "abc"
    assert list(store.keys()) == ["abc"]
    assert store.get("missing") is None