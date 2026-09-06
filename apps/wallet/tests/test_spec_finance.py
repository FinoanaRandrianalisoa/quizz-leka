import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client

from apps.wallet.models import Portefeuille, LedgerEntry, PlatformeWallet
from apps.matches.models import Match, Tour


CREDIT = Decimal("1000000.00")


@pytest.fixture(autouse=True)
def donnees():
    from apps.matches import services as match_services

    call_command("seed_questions", verbosity=0)
    yield
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


def _remise_a_zero_capital():
    pw = PlatformeWallet.singleton()
    pw.capital = Decimal("0.00")
    pw.save(update_fields=["capital"])
    return pw


@pytest.mark.django_db
def test_credit_initial_demo_idempotent(client):
    tok = _register(client, "demo@example.mg", "Demo")
    _gql(client, "{ monPortefeuille { soldeRecharge soldeTotal modeDemo } }", tok)

    pf = Portefeuille.objects.get(utilisateur__email="demo@example.mg")
    assert pf.solde_recharge == CREDIT
    assert pf.ledger_entries.filter(type=LedgerEntry.Type.DEMO_INITIAL_CREDIT, statut=LedgerEntry.Statut.SUCCES).count() == 1


@pytest.mark.django_db
def test_pin_definir_deverrouiller_et_recharger_demo(client):
    tok = _register(client, "pin@example.mg", "PinUser")

    # Sans PIN, la recharge est refusée (protection demandée par la spec).
    sans_pin = _gql(
        client,
        'mutation { rechargerPortefeuille(idempotencyKey: "rech-0") { soldeTotal } }',
        tok,
    )
    assert sans_pin["errors"][0]["extensions"]["code"] == "WALLET_PIN_NOT_SET"

    # Définition du PIN (nécessite une confirmation identique).
    pb = _gql(
        client,
        'mutation { definirPinPortefeuille(pin: "1234", pinConfirmation: "9999") { pinDefini } }',
        tok,
    )
    assert pb["errors"][0]["extensions"]["code"] == "WALLET_PIN_MISMATCH"
    ok = _gql(
        client,
        'mutation { definirPinPortefeuille(pin: "1234", pinConfirmation: "1234") { pinDefini } }',
        tok,
    )
    assert ok["data"]["definirPinPortefeuille"]["pinDefini"] is True

    # Le portefeuille est verrouillé tant que le PIN n'est pas (re)saisi.
    verrouille = _gql(
        client,
        'mutation { rechargerPortefeuille(idempotencyKey: "rech-1") { soldeTotal } }',
        tok,
    )
    assert verrouille["errors"][0]["extensions"]["code"] == "WALLET_UNLOCK_REQUIRED"

    dec = _gql(
        client,
        'mutation { deverrouillerPortefeuille(pin: "1234") { portefeuilleDeverrouille } }',
        tok,
    )
    assert dec["data"]["deverrouillerPortefeuille"]["portefeuilleDeverrouille"] is True

    recharge = _gql(
        client,
        'mutation { rechargerPortefeuille(idempotencyKey: "rech-1") { soldeRecharge rechargeDemoDisponible } }',
        tok,
    )
    assert recharge["data"]["rechargerPortefeuille"]["soldeRecharge"] == str(CREDIT * 2)
    assert recharge["data"]["rechargerPortefeuille"]["rechargeDemoDisponible"] is False

    # Limite d'une recharge par jour.
    seconde = _gql(
        client,
        'mutation { rechargerPortefeuille(idempotencyKey: "rech-2") { soldeTotal } }',
        tok,
    )
    assert seconde["errors"][0]["extensions"]["code"] == "WALLET_RECHARGE_LIMIT"


@pytest.mark.django_db
def test_pin_brute_force_verrouille_le_portefeuille(client):
    tok = _register(client, "brute@example.mg", "Brute")
    _gql(client, 'mutation { definirPinPortefeuille(pin: "1234", pinConfirmation: "1234") { pinDefini } }', tok)

    for i in range(5):
        rep = _gql(
            client,
            'mutation { deverrouillerPortefeuille(pin: "0000") { portefeuilleDeverrouille } }',
            tok,
        )
        code = rep["errors"][0]["extensions"]["code"]
        if i < 4:
            assert code == "WALLET_PIN_INVALID"
        else:
            assert code == "WALLET_LOCKED"

    pf = Portefeuille.objects.get(utilisateur__email="brute@example.mg")
    assert pf.is_locked is True
    assert pf.locked_until is not None


@pytest.mark.django_db
def test_duel_mise_asymetrique_et_reglement_avec_commissions(client):
    _remise_a_zero_capital()
    tok_a = _register(client, "hote@example.mg", "Hote")
    tok_b = _register(client, "invi@example.mg", "Invi")

    from apps.themes.models import Theme

    theme = Theme.objects.first()
    creer = _gql(
        client,
        f'mutation {{ creerPartie(themeId: {theme.pk}, mise: "2000", scoreCible: 2) {{ id mise }} }}',
        tok_a,
    )
    assert "errors" not in creer, creer
    match_id = int(creer["data"]["creerPartie"]["id"])

    # L'invité propose une mise différente : la mise effective = MIN(2000, 1000).
    rejoindre = _gql(
        client,
        f'mutation {{ rejoindrePartie(matchId: {match_id}, mise: "1000") {{ statut miseEffective }} }}',
        tok_b,
    )
    assert "errors" not in rejoindre, rejoindre
    assert rejoindre["data"]["rejoindrePartie"]["miseEffective"] == "1000.00"

    pf_hote = Portefeuille.objects.get(utilisateur__email="hote@example.mg")
    pf_invite = Portefeuille.objects.get(utilisateur__email="invi@example.mg")
    # Réservation hôte 2000 → surplus 1000 libéré ; l'invité 1000 réservé.
    assert pf_hote.solde_recharge == CREDIT - Decimal("1000.00")
    assert pf_hote.solde_bloque == Decimal("1000.00")
    assert pf_invite.solde_recharge == CREDIT - Decimal("1000.00")
    assert pf_invite.solde_bloque == Decimal("1000.00")

    # L'hôte répond correctement aux deux tours : score cible atteint.
    for _ in range(2):
        tour = Tour.objects.filter(match_id=match_id, statut=Tour.Statut.EN_COURS).order_by("-numero").first()
        bonne = tour.question.reponses.get(est_correcte=True)
        rep = _gql(
            client,
            f'mutation {{ soumettreReponse(tourId: {tour.pk}, reponseId: {bonne.pk}) }}',
            tok_a,
        )
        assert "errors" not in rep, rep
    assert rep["data"]["soumettreReponse"] is True

    match = Match.objects.get(pk=match_id)
    assert match.statut == Match.Statut.TERMINE
    assert match.vainqueur_id is not None

    pf_hote.refresh_from_db()
    pf_invite.refresh_from_db()
    # Hôte gagnant : pot net 1600 (2000 − 2×200), sa mise engagée consommée.
    assert pf_hote.solde_recharge == CREDIT - Decimal("1000.00")
    assert pf_hote.solde_gains == Decimal("1600.00")
    assert pf_hote.solde_bloque == Decimal("0.00")
    # Invité perdant : sa mise 1000 est consommée.
    assert pf_invite.solde_recharge == CREDIT - Decimal("1000.00")
    assert pf_invite.solde_bloque == Decimal("0.00")

    entres_hote = pf_hote.ledger_entries.values_list("type", "montant")
    assert (LedgerEntry.Type.MISE_LIBEREE, Decimal("1000.00")) in list(entres_hote)
    assert (LedgerEntry.Type.GAIN, Decimal("1600.00")) in list(entres_hote)
    assert (LedgerEntry.Type.COMMISSION, Decimal("-400.00")) in list(entres_hote)
    assert (LedgerEntry.Type.PERTE, Decimal("-1000.00")) in list(pf_invite.ledger_entries.values_list("type", "montant"))

    # Capital plateforme = 2 × 20 % × mise effective.
    assert PlatformeWallet.objects.get(pk=1).capital == Decimal("400.00")


@pytest.mark.django_db
def test_duel_egalite_rembourse_sans_commission(client):
    _remise_a_zero_capital()
    _register(client, "hote2@example.mg", "Hote2")
    _register(client, "invi2@example.mg", "Invi2")

    from apps.matches import services as match_services
    from apps.themes.models import Theme
    from django.contrib.auth import get_user_model

    Utilisateur = get_user_model()
    hote = Utilisateur.objects.get(email="hote2@example.mg")
    invite = Utilisateur.objects.get(email="invi2@example.mg")

    theme = Theme.objects.first()
    match = match_services.creer_partie(hote, theme_id=theme.pk, mise=Decimal("500"), score_cible=1)
    match_services.rejoindre_partie(invite, match.pk, mise=Decimal("500"))

    # Égalité de score → règlement en annulation (restitution 100 %, sans commission).
    match.score_hote = 1
    match.score_invite = 1
    match.save(update_fields=["score_hote", "score_invite"])
    match_services._cloturer(match, False)
    match.refresh_from_db()
    assert match.statut == Match.Statut.ANNULE

    # Égalité : les mises réservées sont restituées à 100 % sans commission.
    for email in ("hote2@example.mg", "invi2@example.mg"):
        pf = Portefeuille.objects.get(utilisateur__email=email)
        assert pf.solde_recharge == CREDIT
        assert pf.solde_bloque == Decimal("0.00")
        assert pf.solde_gains == Decimal("0.00")
    assert PlatformeWallet.objects.get(pk=1).capital == Decimal("0.00")