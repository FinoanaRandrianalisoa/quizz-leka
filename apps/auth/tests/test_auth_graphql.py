import base64
import json

import pytest
from django.test import Client

from apps.users.models import Utilisateur


@pytest.fixture
def client():
    return Client()


def _gql(client, query, token=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    r = client.post(
        "/graphql/",
        data={"query": query},
        content_type="application/json",
        **headers,
    )
    return json.loads(r.content)


@pytest.mark.django_db
def test_register_login_profil(client):
    reg = _gql(
        client,
        'mutation { register(input: { email: "a@example.mg", pseudo: "Alice", password: "MotDePasse1!", villeOrigine: "Antananarivo", firstName: "Alice", lastName: "Rasoa" }) { accessToken utilisateur { pseudo villeOrigine firstName lastName } } }',
    )
    assert "errors" not in reg, reg
    token = reg["data"]["register"]["accessToken"]
    utilisateur = reg["data"]["register"]["utilisateur"]
    assert utilisateur["villeOrigine"] == "Antananarivo"
    assert utilisateur["firstName"] == "Alice"
    assert utilisateur["lastName"] == "Rasoa"

    login = _gql(
        client,
        'mutation { login(email: "A@example.mg", password: "MotDePasse1!") { accessToken } }',
    )
    assert "errors" not in login, login

    profil = _gql(client, "{ profil { utilisateur { pseudo villeOrigine firstName lastName } } }", token=token)
    assert profil["data"]["profil"]["utilisateur"]["pseudo"] == "Alice"
    assert profil["data"]["profil"]["utilisateur"]["villeOrigine"] == "Antananarivo"


@pytest.mark.django_db
def test_register_accepts_valid_data_url_images(client):
    payload = b"fake-png-content"
    data_url = "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    resp = _gql(
        client,
        f'mutation {{ register(input: {{ email: "image@example.mg", pseudo: "ImageUser", password: "MotDePasse1!", photoProfil: "{data_url}", photoCouverture: "{data_url}" }}) {{ accessToken utilisateur {{ pseudo photoProfil photoCouverture }} }} }}',
    )
    assert "errors" not in resp, resp
    user = Utilisateur.objects.get(email="image@example.mg")
    assert user.photo_profil
    assert user.photo_couverture
    assert "photoProfil" in resp["data"]["register"]["utilisateur"]
    assert "photoCouverture" in resp["data"]["register"]["utilisateur"]


@pytest.mark.django_db
def test_email_duplique_code_normalise(client):
    query = 'mutation { register(input: { email: "dup@example.mg", pseudo: "Dup", password: "MotDePasse1!" }) { accessToken } }'
    assert "errors" not in _gql(client, query)
    resp = _gql(client, query.replace('email: "dup@example.mg"', 'email: "DUP@example.mg"').replace('pseudo: "Dup"', 'pseudo: "Dup2"'))
    assert resp["errors"][0]["extensions"]["code"] == "AUTH_EMAIL_ALREADY_TAKEN"


@pytest.mark.django_db
def test_profil_anonyme_renvoie_permission_denied(client):
    resp = _gql(client, "{ profil { utilisateur { pseudo } } }")
    assert resp["errors"][0]["extensions"]["code"] == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_login_par_telephone_et_date_naissance(client):
    reg = _gql(
        client,
        'mutation { register(input: { email: "tel@example.mg", pseudo: "TelephoneUser", password: "MotDePasse1!", telephone: "0341234567", dateNaissance: "2000-05-15", firstName: "Finoana", villeOrigine: "Fianarantsoa" }) { accessToken utilisateur { telephone dateNaissance firstName villeOrigine } } }',
    )
    assert "errors" not in reg, reg
    utilisateur = reg["data"]["register"]["utilisateur"]
    assert utilisateur["telephone"] == "0341234567"
    assert utilisateur["dateNaissance"] == "2000-05-15"

    login = _gql(client, 'mutation { login(email: "0341234567", password: "MotDePasse1!") { accessToken } }')
    assert "errors" not in login, login

    login_email = _gql(client, 'mutation { login(email: "TEL@example.mg", password: "MotDePasse1!") { accessToken } }')
    assert "errors" not in login_email, login_email


@pytest.mark.django_db
def test_update_profil_complet(client):
    reg = _gql(
        client,
        'mutation { register(input: { email: "up@example.mg", pseudo: "Up1", password: "MotDePasse1!" }) { accessToken utilisateur { id } } }',
    )
    token = reg["data"]["register"]["accessToken"]
    payload = b"fake-png-content"
    data_url = "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    upd = _gql(
        client,
        f'mutation {{ updateProfil(input: {{ firstName: "Finoana", lastName: "Rabe", dateNaissance: "2001-01-01", telephone: "0321112233", villeOrigine: "Fianarantsoa", photoProfil: "{data_url}" }}) {{ firstName lastName dateNaissance telephone villeOrigine photoProfil }} }}',
        token=token,
    )
    assert "errors" not in upd, upd
    updated = upd["data"]["updateProfil"]
    assert updated["firstName"] == "Finoana"
    assert updated["lastName"] == "Rabe"
    assert updated["dateNaissance"] == "2001-01-01"
    assert updated["telephone"] == "0321112233"
    assert updated["villeOrigine"] == "Fianarantsoa"
    assert updated["photoProfil"]


@pytest.mark.django_db
def test_inscription_sans_email_par_telephone(client):
    reg = _gql(
        client,
        'mutation { register(input: { pseudo: "SansEmail", password: "MotDePasse1!", telephone: "0339876543", firstName: "Tiana", lastName: "Rakoto", dateNaissance: "1998-03-22", villeOrigine: "Toamasina" }) { accessToken utilisateur { email telephone } } }',
    )
    assert "errors" not in reg, reg
    assert reg["data"]["register"]["utilisateur"]["email"] is None
    assert reg["data"]["register"]["utilisateur"]["telephone"] == "0339876543"

    login = _gql(client, 'mutation { login(email: "0339876543", password: "MotDePasse1!") { accessToken } }')
    assert "errors" not in login, login


@pytest.mark.django_db
def test_pseudo_info_suggestion_et_disponibilite(client):
    _gql(
        client,
        'mutation { register(input: { email: "b@example.mg", pseudo: "Rakoto", password: "MotDePasse1!", firstName: "Bob", lastName: "Rakoto" }) { accessToken } }',
    )

    libre = _gql(client, '{ pseudoInfo(pseudo: "alice") { disponible suggestion } }')
    assert "errors" not in libre, libre
    assert libre["data"]["pseudoInfo"] == {"disponible": True, "suggestion": "alice"}

    pris = _gql(client, '{ pseudoInfo(pseudo: "Rakoto123") { disponible suggestion } }')
    assert "errors" not in pris, pris
    assert pris["data"]["pseudoInfo"]["disponible"] is False
    assert pris["data"]["pseudoInfo"]["suggestion"] == "rakoto1"


@pytest.mark.django_db
def test_erreur_interne_masquee(client):
    # Token valide côté décodage mais utilisateur inexistant -> erreur générique.
    resp = _gql(client, "{ monPortefeuille { soldeTotal } }", token="token.invalide")
    assert resp["errors"][0]["extensions"]["code"] == "PERMISSION_DENIED"