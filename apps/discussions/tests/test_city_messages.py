import json

import pytest

from apps.discussions.models import Ville
from apps.users.models import Utilisateur


@pytest.fixture
def client():
    from django.test import Client

    return Client()


def _gql(client, query, token=None, variables=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    response = client.post(
        "/graphql/",
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )
    return json.loads(response.content)


@pytest.mark.django_db
def test_messages_salon_sont_isoles_par_ville(client):
    user = Utilisateur.objects.create_user(email="ville@example.mg", pseudo="VilleUser", password="MotDePasse1!")
    antananarivo = Ville.objects.create(nom="Antananarivo Test", slug="antananarivo-test-unique")
    toamasina = Ville.objects.create(nom="Toamasina Test", slug="toamasina-test-unique")

    login = _gql(client, 'mutation { login(email: "ville@example.mg", password: "MotDePasse1!") { accessToken } }')
    token = login["data"]["login"]["accessToken"]

    city_a = _gql(
        client,
        "mutation($villeSlug: String!, $contenu: String!) { envoyerMessageVille(villeSlug: $villeSlug, contenu: $contenu) { id contenu } }",
        token=token,
        variables={"villeSlug": antananarivo.slug, "contenu": "Bonjour Antananarivo"},
    )
    assert "errors" not in city_a, city_a

    city_b = _gql(
        client,
        "mutation($villeSlug: String!, $contenu: String!) { envoyerMessageVille(villeSlug: $villeSlug, contenu: $contenu) { id contenu } }",
        token=token,
        variables={"villeSlug": toamasina.slug, "contenu": "Bonjour Toamasina"},
    )
    assert "errors" not in city_b, city_b

    history_antananarivo = _gql(
        client,
        "query($villeSlug: String!) { messagesSalon(villeSlug: $villeSlug) { contenu } }",
        token=token,
        variables={"villeSlug": antananarivo.slug},
    )
    history_toamasina = _gql(
        client,
        "query($villeSlug: String!) { messagesSalon(villeSlug: $villeSlug) { contenu } }",
        token=token,
        variables={"villeSlug": toamasina.slug},
    )

    assert "errors" not in history_antananarivo, history_antananarivo
    assert "errors" not in history_toamasina, history_toamasina
    assert any(item["contenu"] == "Bonjour Antananarivo" for item in history_antananarivo["data"]["messagesSalon"])
    assert any(item["contenu"] == "Bonjour Toamasina" for item in history_toamasina["data"]["messagesSalon"])
    assert all(item["contenu"] != "Bonjour Toamasina" for item in history_antananarivo["data"]["messagesSalon"])
    assert all(item["contenu"] != "Bonjour Antananarivo" for item in history_toamasina["data"]["messagesSalon"])
