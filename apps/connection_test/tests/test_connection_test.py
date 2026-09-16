from django.test import Client


def test_ping_is_fast_and_has_no_db():
    client = Client()
    response = client.get("/api/connection-test/ping/")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_download_respects_size_cap():
    client = Client()
    response = client.get("/api/connection-test/download/?size=2048")
    assert response.status_code == 200
    assert len(response.content) == 2048

    huge = client.get("/api/connection-test/download/?size=99999999")
    assert huge.status_code == 200
    assert len(huge.content) <= 256 * 1024


def test_upload_discards_payload():
    client = Client()
    response = client.post(
        "/api/connection-test/upload/",
        data=b"abcdef",
        content_type="application/octet-stream",
    )
    assert response.status_code == 200
    assert response.json()["bytes"] == 6
