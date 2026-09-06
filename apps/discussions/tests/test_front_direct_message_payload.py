import json

import pytest

from apps.discussions.models import MessageAmi, Ville
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
def test_envoyer_message_ami_with_front_field_set(client):
    user_a = Utilisateur.objects.create_user(email="front-a@example.mg", pseudo="FrontA", password="MotDePasse1!")
    user_b = Utilisateur.objects.create_user(email="front-b@example.mg", pseudo="FrontB", password="MotDePasse1!")
    DemandeAmi.objects.create(demandeur=user_a, receveur=user_b, statut=DemandeAmi.Statut.ACCEPTEE)

    login = _gql(client, 'mutation { login(email: "front-a@example.mg", password: "MotDePasse1!") { accessToken } }')
    token = login["data"]["login"]["accessToken"]

    query = '''
    mutation($amiId: Int!, $contenu: String!) {
      envoyerMessageAmi(amiId: $amiId, contenu: $contenu) {
        id
        contenu
        creeLe
        expediteur {
          id pseudo email role firstName lastName villeOrigine photoProfil photoCouverture enLigne dateJoined codeParrain
        }
        destinataire {
          id pseudo email role firstName lastName villeOrigine photoProfil photoCouverture enLigne dateJoined codeParrain
        }
      }
    }
    '''

    response = _gql(client, query, token=token, variables={"amiId": user_b.id, "contenu": "Salut Front"})
    assert "errors" not in response, response
    assert response["data"]["envoyerMessageAmi"]["contenu"] == "Salut Front"


@pytest.mark.django_db
def test_discussions_unifiees(client):
    user_a = Utilisateur.objects.create_user(email="disc-a@example.mg", pseudo="DiscA", password="MotDePasse1!")
    user_b = Utilisateur.objects.create_user(email="disc-b@example.mg", pseudo="DiscB", password="MotDePasse1!")
    DemandeAmi.objects.create(demandeur=user_a, receveur=user_b, statut=DemandeAmi.Statut.ACCEPTEE)
    Ville.objects.get_or_create(nom="Antananarivo", slug="antananarivo")

    login = _gql(client, 'mutation { login(email: "disc-a@example.mg", password: "MotDePasse1!") { accessToken } }')
    token = login["data"]["login"]["accessToken"]

    _gql(client, 'mutation { envoyerMessageAmi(amiId: %s, contenu: "Bonjour") { id } }' % user_b.id, token=token)
    _gql(client, 'mutation { envoyerMessageVille(villeSlug: "antananarivo", contenu: "Bienvenue Tana") { id } }', token=token)

    response = _gql(
        client,
        """
        {
          discussions {
            type
            identifiant
            dernierMessage
            nonLus
            adversaire { pseudo }
            ville { nom }
          }
        }
        """,
        token=token,
    )
    assert "errors" not in response, response
    convos = response["data"]["discussions"]
    assert len(convos) >= 2
    ami = next(c for c in convos if c["type"] == "ami")
    groupe = next(c for c in convos if c["type"] == "groupe" and c["ville"]["nom"] == "Antananarivo")
    assert ami["dernierMessage"] == "Bonjour"
    assert ami["adversaire"]["pseudo"] == "DiscB"
    assert groupe["dernierMessage"] == "Bienvenue Tana"
    assert groupe["ville"]["nom"] == "Antananarivo"
    assert groupe["nonLus"] == 0

    sent = _gql(client, 'mutation { envoyerMessageAmi(amiId: %s, contenu: "Suite") { id } }' % user_b.id, token=token)
    assert "errors" not in sent, sent
    updated = _gql(client, "{ discussions { identifiant dernierMessage nonLus } }", token=token)
    amis = [c for c in updated["data"]["discussions"] if c["identifiant"] == f"ami:{user_b.id}"]
    assert amis and amis[0]["dernierMessage"] == "Suite"
