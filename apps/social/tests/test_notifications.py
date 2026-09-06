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
def test_accepter_demande_cree_une_notification_pour_le_demandeur(client):
    demandeur = Utilisateur.objects.create_user(email="demandeur@example.mg", pseudo="Demandeur", password="MotDePasse1!")
    receveur = Utilisateur.objects.create_user(email="receveur@example.mg", pseudo="Receveur", password="MotDePasse1!")

    demande = DemandeAmi.objects.create(demandeur=demandeur, receveur=receveur)

    login = _gql(
        client,
        'mutation { login(email: "receveur@example.mg", password: "MotDePasse1!") { accessToken } }',
    )
    token = login["data"]["login"]["accessToken"]

    resp = _gql(
        client,
        "mutation($id: Int!, $accepter: Boolean!) { repondreDemandeAmi(demandeId: $id, accepter: $accepter) }",
        token=token,
        variables={"id": demande.id, "accepter": True},
    )

    assert "errors" not in resp, resp
    assert resp["data"]["repondreDemandeAmi"] is True

    demandeur_login = _gql(
        client,
        'mutation { login(email: "demandeur@example.mg", password: "MotDePasse1!") { accessToken } }',
    )

    notification = _gql(
        client,
        "{ mesNotifications { id type titre message lu } }",
        token=demandeur_login["data"]["login"]["accessToken"],
    )
    assert "errors" not in notification, notification
    assert notification["data"]["mesNotifications"]

    from apps.social.models import Notification
    assert Notification.objects.filter(destinataire=demandeur, type=Notification.Type.AMI_ACCEPTE).exists()
    notif = Notification.objects.get(destinataire=demandeur, type=Notification.Type.AMI_ACCEPTE)
    assert "a accepté votre demande d'ami" in notif.message.lower()


@pytest.mark.django_db
def test_demandes_amis_envoyees_affiche_le_receveur_et_l_heure(client):
    demandeur = Utilisateur.objects.create_user(email="demandeur@example.mg", pseudo="Demandeur", password="MotDePasse1!")
    receveur = Utilisateur.objects.create_user(email="receveur@example.mg", pseudo="Receveur", password="MotDePasse1!")
    DemandeAmi.objects.create(demandeur=demandeur, receveur=receveur)

    login = _gql(
        client,
        'mutation { login(email: "demandeur@example.mg", password: "MotDePasse1!") { accessToken } }',
    )
    token = login["data"]["login"]["accessToken"]

    resp = _gql(
        client,
        "{ demandesAmisEnvoyees { id statut creeLe receveur { pseudo villeOrigine } } }",
        token=token,
    )

    assert "errors" not in resp, resp
    demandes = resp["data"]["demandesAmisEnvoyees"]
    assert len(demandes) == 1
    demande = demandes[0]
    assert demande["statut"] == DemandeAmi.Statut.EN_ATTENTE
    assert demande["creeLe"]
    assert demande["receveur"]["pseudo"] == "Receveur"


@pytest.mark.django_db
def test_notification_expose_l_expediteur(client):
    demandeur = Utilisateur.objects.create_user(email="demandeur@example.mg", pseudo="Demandeur", password="MotDePasse1!")
    receveur = Utilisateur.objects.create_user(email="receveur@example.mg", pseudo="Receveur", password="MotDePasse1!")
    DemandeAmi.objects.create(demandeur=demandeur, receveur=receveur)

    login = _gql(
        client,
        'mutation { login(email: "receveur@example.mg", password: "MotDePasse1!") { accessToken } }',
    )
    token = login["data"]["login"]["accessToken"]

    _gql(
        client,
        "mutation($id: Int!, $accepter: Boolean!) { repondreDemandeAmi(demandeId: $id, accepter: $accepter) }",
        token=token,
        variables={"id": DemandeAmi.objects.get().id, "accepter": True},
    )

    login_demandeur = _gql(
        client,
        'mutation { login(email: "demandeur@example.mg", password: "MotDePasse1!") { accessToken } }',
    )
    resp = _gql(
        client,
        "{ mesNotifications { id titre message expediteur { pseudo villeOrigine } } }",
        token=login_demandeur["data"]["login"]["accessToken"],
    )
    assert "errors" not in resp, resp
    notif = resp["data"]["mesNotifications"][0]
    assert notif["expediteur"]["pseudo"] == "Receveur"
