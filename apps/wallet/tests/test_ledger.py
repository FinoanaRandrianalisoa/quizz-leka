import json
from decimal import Decimal as Decimal_

import pytest
from django.test import Client

from apps.wallet.models import Portefeuille, LedgerEntry

CREDIT_INITIAL = 1000000.00


@pytest.fixture
def jeton():
    c = Client()
    r = c.post(
        "/graphql/",
        data={"query": 'mutation { register(input: { email: "wallet@example.mg", pseudo: "Wallet", password: "MotDePasse1!" }) { accessToken } }'},
        content_type="application/json",
    )
    return json.loads(r.content)["data"]["register"]["accessToken"]


def _depot(client, token, clé, montant="50.00"):
    r = client.post(
        "/graphql/",
        data={"query": f'mutation {{ effectuerDepot(montant: "{montant}", method: "MVola", idempotencyKey: "{clé}", phoneNumber: "0340000000") {{ soldeRecharge soldeTotal }} }}'},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    return json.loads(r.content)


@pytest.mark.django_db
def test_depot_majore_ledger(jeton):
    c = Client()
    resp = _depot(c, jeton, "clé-001")
    assert "errors" not in resp, resp
    # Le crédit initial DEMO (+1 000 000 Ar) s'ajoute au dépôt.
    assert resp["data"]["effectuerDepot"]["soldeRecharge"] == "1000050.00"

    pf = Portefeuille.objects.get(utilisateur__email="wallet@example.mg")
    assert pf.solde_recharge == Decimal_("1000050.00")
    assert (
        pf.ledger_entries.filter(
            type=LedgerEntry.Type.DEMO_INITIAL_CREDIT, statut=LedgerEntry.Statut.SUCCES
        ).count()
        == 1
    )
    assert pf.ledger_entries.filter(type=LedgerEntry.Type.DEPOT, statut=LedgerEntry.Statut.SUCCES).count() == 1


@pytest.mark.django_db
def test_depot_idempotent(jeton):
    c = Client()
    premier = _depot(c, jeton, "clé-002")
    second = _depot(c, jeton, "clé-002")
    assert "errors" not in premier
    assert second["errors"][0]["extensions"]["code"] == "WALLET_IDEMPOTENCY_CONFLICT"

    pf = Portefeuille.objects.get(utilisateur__email="wallet@example.mg")
    assert pf.solde_recharge == Decimal_("1000050.00")


@pytest.mark.django_db
def test_retrait_sans_otp_refuse(jeton):
    c = Client()
    r = c.post(
        "/graphql/",
        data={"query": 'mutation { demanderRetrait(montant: "10.00", phoneNumber: "0340000000", otpToken: "pas-otp", idempotencyKey: "clé-003") { soldeRecharge } }'},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {jeton}",
    )
    resp = json.loads(r.content)
    assert resp["errors"][0]["extensions"]["code"] == "AUTH_INVALID_OTP"