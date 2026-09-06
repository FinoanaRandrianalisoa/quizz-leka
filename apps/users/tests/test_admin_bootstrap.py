import json

import pytest
from django.test import Client

from apps.users.bootstrap import ensure_bootstrap_admin
from apps.users.models import Utilisateur


@pytest.fixture
def client():
    return Client()


def _gql(client, query, token=None, variables=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    r = client.post(
        "/graphql/",
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )
    return json.loads(r.content)


def _register(client, email, pseudo, password="MotDePasse1!"):
    resp = _gql(
        client,
        """
        mutation($input: RegisterInput!) {
          register(input: $input) { accessToken utilisateur { id pseudo role } }
        }
        """,
        variables={"input": {"email": email, "pseudo": pseudo, "password": password}},
    )
    assert "errors" not in resp, resp
    return resp["data"]["register"]


@pytest.mark.django_db
def test_ensure_bootstrap_admin_cree_le_compte(settings):
    settings.BOOTSTRAP_ADMIN_ENABLED = True
    settings.BOOTSTRAP_ADMIN_EMAIL = "admin@quizz.mg"
    settings.BOOTSTRAP_ADMIN_PASSWORD = "Admin123!"
    settings.BOOTSTRAP_ADMIN_PSEUDO = "Admin"
    ensure_bootstrap_admin()
    admin = Utilisateur.objects.get(email="admin@quizz.mg")
    assert admin.role == "ADMIN"
    assert admin.is_superuser
    ensure_bootstrap_admin()
    assert Utilisateur.objects.filter(email="admin@quizz.mg").count() == 1


@pytest.mark.django_db
def test_admin_peut_promouvoir_un_joueur(client, settings):
    settings.BOOTSTRAP_ADMIN_ENABLED = True
    settings.BOOTSTRAP_ADMIN_EMAIL = "admin@quizz.mg"
    settings.BOOTSTRAP_ADMIN_PASSWORD = "Admin123!"
    ensure_bootstrap_admin()
    joueur = _register(client, "joueur@example.mg", "JoueurTest")
    login = _gql(
        client,
        'mutation { login(email: "admin@quizz.mg", password: "Admin123!") { accessToken } }',
    )
    assert "errors" not in login, login
    token = login["data"]["login"]["accessToken"]
    promo = _gql(
        client,
        """
        mutation($id: ID!) {
          changerRole(utilisateurId: $id, role: "ADMIN") { pseudo role }
        }
        """,
        token=token,
        variables={"id": joueur["utilisateur"]["id"]},
    )
    assert "errors" not in promo, promo
    assert promo["data"]["changerRole"]["role"] == "ADMIN"


@pytest.mark.django_db
def test_joueur_ne_peut_pas_promouvoir(client):
    a = _register(client, "a@example.mg", "Alice")
    b = _register(client, "b@example.mg", "Bob")
    promo = _gql(
        client,
        """
        mutation($id: ID!) {
          changerRole(utilisateurId: $id, role: "ADMIN") { role }
        }
        """,
        token=a["accessToken"],
        variables={"id": b["utilisateur"]["id"]},
    )
    assert promo["errors"][0]["extensions"]["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_classement_et_themes_publics(client):
    _register(client, "c@example.mg", "Coco")
    classmt = _gql(client, "{ classement { rang utilisateur { pseudo } parties } }")
    assert "errors" not in classmt, classmt
    assert classmt["data"]["classement"][0]["utilisateur"]["pseudo"] == "Coco"
    themes = _gql(client, "{ themes { nom nombreQuestions } }")
    assert "errors" not in themes, themes
    stats = _gql(client, "{ statsPlateforme { joueurs questions } }")
    assert stats["data"]["statsPlateforme"]["joueurs"] >= 1


@pytest.mark.django_db
def test_liste_utilisateurs_disponible_pour_invitation(client, settings):
    settings.BOOTSTRAP_ADMIN_ENABLED = True
    settings.BOOTSTRAP_ADMIN_EMAIL = "admin@quizz.mg"
    settings.BOOTSTRAP_ADMIN_PASSWORD = "Admin123!"
    ensure_bootstrap_admin()
    player = _register(client, "lambda@example.mg", "Lambda")
    _register(client, "joueur2@example.mg", "JoueurDeux")

    resp = _gql(
        client,
        "{ utilisateurs { email role } }",
        token=player["accessToken"],
    )
    assert "errors" not in resp, resp

    emails = {u["email"] for u in resp["data"]["utilisateurs"]}
    assert "admin@quizz.mg" in emails
    assert "joueur2@example.mg" in emails

    roles = {u["email"]: u["role"] for u in resp["data"]["utilisateurs"]}
    assert roles["admin@quizz.mg"] == "ADMIN"
    assert roles["joueur2@example.mg"] == "JOUEUR"


@pytest.mark.django_db
def test_joueur_peut_lister_les_autres_utilisateurs_pour_invitation(client, settings):
    settings.BOOTSTRAP_ADMIN_ENABLED = True
    settings.BOOTSTRAP_ADMIN_EMAIL = "admin@quizz.mg"
    settings.BOOTSTRAP_ADMIN_PASSWORD = "Admin123!"
    ensure_bootstrap_admin()

    player = _register(client, "joueur@example.mg", "JoueurA")
    _register(client, "autre@example.mg", "AutreJoueur")

    resp = _gql(
        client,
        "{ utilisateurs { id pseudo role } }",
        token=player["accessToken"],
    )

    assert "errors" not in resp, resp
    users = {u["pseudo"] for u in resp["data"]["utilisateurs"]}
    assert "JoueurA" in users
    assert "AutreJoueur" in users
    assert "Admin" in users
