import json

import pytest

from apps.themes.models import Theme
from apps.users.bootstrap import ensure_bootstrap_admin


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
def test_admin_peut_creer_et_modifier_des_questions(client, settings):
    settings.BOOTSTRAP_ADMIN_ENABLED = True
    settings.BOOTSTRAP_ADMIN_EMAIL = "admin@quizz.mg"
    settings.BOOTSTRAP_ADMIN_PASSWORD = "Admin123!"
    settings.BOOTSTRAP_ADMIN_PSEUDO = "Admin"
    ensure_bootstrap_admin()

    login = _gql(
        client,
        'mutation { login(email: "admin@quizz.mg", password: "Admin123!") { accessToken } }',
    )
    assert "errors" not in login, login
    token = login["data"]["login"]["accessToken"]

    theme = Theme.objects.create(nom="Culture", slug="culture", description="")
    created = _gql(
        client,
        """
        mutation($themeId: Int!, $texte: String!, $reponses: [ReponseInput!]!) {
          createQuestion(themeId: $themeId, texte: $texte, reponses: $reponses) {
            id
            texte
            choix { id texte estCorrecte }
          }
        }
        """,
        token=token,
        variables={
            "themeId": theme.id,
            "texte": "Quelle est la capitale de Madagascar ?",
            "reponses": [
                {"texte": "Antananarivo", "estCorrecte": True},
                {"texte": "Toamasina", "estCorrecte": False},
                {"texte": "Mahajanga", "estCorrecte": False},
                {"texte": "Fianarantsoa", "estCorrecte": False},
            ],
        },
    )
    assert "errors" not in created, created
    qid = int(created["data"]["createQuestion"]["id"])
    assert created["data"]["createQuestion"]["choix"][0]["estCorrecte"] is True

    updated = _gql(
        client,
        """
        mutation($questionId: Int!, $texte: String!, $reponses: [ReponseInput!]!) {
          updateQuestion(questionId: $questionId, texte: $texte, reponses: $reponses) {
            id
            texte
            choix { texte estCorrecte }
          }
        }
        """,
        token=token,
        variables={
            "questionId": qid,
            "texte": "Quelle est la capitale administrative de Madagascar ?",
            "reponses": [
                {"texte": "Antananarivo", "estCorrecte": True},
                {"texte": "Nosy Be", "estCorrecte": False},
                {"texte": "Toliara", "estCorrecte": False},
                {"texte": "Antsirabe", "estCorrecte": False},
            ],
        },
    )
    assert "errors" not in updated, updated
    assert updated["data"]["updateQuestion"]["texte"] == "Quelle est la capitale administrative de Madagascar ?"

    deleted = _gql(
        client,
        "mutation($questionId: Int!) { deleteQuestion(questionId: $questionId) }",
        token=token,
        variables={"questionId": qid},
    )
    assert "errors" not in deleted, deleted
    assert deleted["data"]["deleteQuestion"] is True
