import json

import pytest

from apps.social.models import DemandeAmi
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
def test_envoyer_et_lire_message_entre_amis(client):
    user_a = Utilisateur.objects.create_user(email="a@example.mg", pseudo="Alice", password="MotDePasse1!")
    user_b = Utilisateur.objects.create_user(email="b@example.mg", pseudo="Bob", password="MotDePasse1!")
    DemandeAmi.objects.create(
        demandeur=user_a,
        receveur=user_b,
        statut=DemandeAmi.Statut.ACCEPTEE,
    )

    login_a = _gql(client, 'mutation { login(email: "a@example.mg", password: "MotDePasse1!") { accessToken } }')
    token_a = login_a["data"]["login"]["accessToken"]

    send = _gql(
        client,
        "mutation($amiId: Int!, $contenu: String!) { envoyerMessageAmi(amiId: $amiId, contenu: $contenu) { id contenu expediteur { pseudo } } }",
        token=token_a,
        variables={"amiId": user_b.id, "contenu": "Salut Bob !"},
    )
    assert "errors" not in send, send
    assert send["data"]["envoyerMessageAmi"]["contenu"] == "Salut Bob !"

    history = _gql(
        client,
        "query($amiId: Int!) { messagesAmi(amiId: $amiId) { id contenu expediteur { pseudo } } }",
        token=token_a,
        variables={"amiId": user_b.id},
    )
    assert "errors" not in history, history
    assert any(item["contenu"] == "Salut Bob !" for item in history["data"]["messagesAmi"])
