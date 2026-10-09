"""Pengujian keamanan BOLA / IDOR (D.3, OWASP API1:2023).

Skenario inti: dua pengguna berbeda. Pengguna B mencoba mengakses objek milik
pengguna A lewat ID. Sistem WAJIB menolak dengan HTTP 403, bukan mengembalikan
data (yang merupakan celah kebocoran data antar-pengguna).
"""

from __future__ import annotations

import pytest

from tests.conftest import auth_header, signup_user


@pytest.fixture
def two_users(client):
    """Siapkan dua pengguna terpisah beserta headernya."""
    alice = signup_user(client, name="Alice", email="alice@example.com")
    bob = signup_user(client, name="Bob", email="bob@example.com")
    return {
        "alice": alice,
        "bob": bob,
        "alice_h": auth_header(alice),
        "bob_h": auth_header(bob),
    }


def _create_history(client, headers, *, visit_date="2025-06-01", visit_day="Sunday", total=1500):
    response = client.post(
        "/api/history",
        headers=headers,
        json={"visit_date": visit_date, "visit_day": visit_day, "visitor_total": total},
    )
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------------------
# BOLA pada resource histori pengunjung
# ------------------------------------------------------------------------------


def test_get_other_users_history_returns_403(client, two_users):
    """BOLA-01: GET /api/history/{id} milik orang lain -> 403."""
    owned = _create_history(client, two_users["alice_h"])

    response = client.get(f"/api/history/{owned['id']}", headers=two_users["bob_h"])
    assert response.status_code == 403, "Celah BOLA: pengguna lain berhasil membaca data"


def test_update_other_users_history_returns_403(client, two_users):
    """BOLA-02: PUT /api/history/{id} milik orang lain -> 403."""
    owned = _create_history(client, two_users["alice_h"])

    response = client.put(
        f"/api/history/{owned['id']}",
        headers=two_users["bob_h"],
        json={"visitor_total": 99999},
    )
    assert response.status_code == 403

    # Pastikan data TIDAK berubah setelah percobaan.
    verify = client.get(f"/api/history/{owned['id']}", headers=two_users["alice_h"])
    assert verify.json()["visitor_total"] == 1500


def test_delete_other_users_history_returns_403(client, two_users):
    """BOLA-03: DELETE /api/history/{id} milik orang lain -> 403."""
    owned = _create_history(client, two_users["alice_h"])

    response = client.delete(f"/api/history/{owned['id']}", headers=two_users["bob_h"])
    assert response.status_code == 403

    # Data masih ada bagi pemiliknya.
    assert client.get(f"/api/history/{owned['id']}", headers=two_users["alice_h"]).status_code == 200


def test_list_history_only_returns_own_records(client, two_users):
    """BOLA-04: daftar histori terfilter per pemilik."""
    _create_history(client, two_users["alice_h"], visit_date="2025-06-01")
    _create_history(client, two_users["bob_h"], visit_date="2025-06-02")

    alice_list = client.get("/api/history", headers=two_users["alice_h"]).json()
    bob_list = client.get("/api/history", headers=two_users["bob_h"]).json()

    assert len(alice_list) == 1
    assert len(bob_list) == 1
    assert alice_list[0]["visit_date"] == "2025-06-01"
    assert bob_list[0]["visit_date"] == "2025-06-02"


def test_missing_history_returns_404_not_500(client, two_users):
    """Penanganan record kosong -> 404, bukan error internal 500."""
    response = client.get("/api/history/999999", headers=two_users["alice_h"])
    assert response.status_code == 404


# ------------------------------------------------------------------------------
# BOLA pada resource hasil prediksi
# ------------------------------------------------------------------------------


def _create_prediction(client, headers, *, visit_day="Sunday", history_id=None):
    payload = {"visit_day": visit_day}
    if history_id is not None:
        payload["visitor_history_id"] = history_id
    response = client.post("/api/predict", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_predict_referencing_other_users_history_returns_403(client, two_users):
    """BOLA-05: prediksi yang merujuk histori milik pengguna lain -> 403."""
    alice_history = _create_history(client, two_users["alice_h"])

    response = client.post(
        "/api/predict",
        headers=two_users["bob_h"],
        json={"visit_day": "Sunday", "visitor_history_id": alice_history["id"]},
    )
    assert response.status_code == 403, "Celah BOLA: referensi lintas pengguna diterima"


def test_predict_with_nonexistent_history_returns_404(client, two_users):
    response = client.post(
        "/api/predict",
        headers=two_users["alice_h"],
        json={"visit_day": "Sunday", "visitor_history_id": 999999},
    )
    assert response.status_code == 404


def test_get_other_users_prediction_returns_403(client, two_users):
    """BOLA-06: GET /api/predictions/{id} milik orang lain -> 403."""
    created = _create_prediction(client, two_users["alice_h"])

    response = client.get(f"/api/predictions/{created['record_id']}", headers=two_users["bob_h"])
    assert response.status_code == 403


def test_delete_other_users_prediction_returns_403(client, two_users):
    """BOLA-07: DELETE /api/predictions/{id} milik orang lain -> 403."""
    created = _create_prediction(client, two_users["alice_h"])

    response = client.delete(f"/api/predictions/{created['record_id']}", headers=two_users["bob_h"])
    assert response.status_code == 403


def test_list_predictions_only_returns_own_records(client, two_users):
    """BOLA-08: daftar prediksi terfilter per pemilik."""
    _create_prediction(client, two_users["alice_h"], visit_day="Sunday")
    _create_prediction(client, two_users["bob_h"], visit_day="Sunday")
    _create_prediction(client, two_users["bob_h"], visit_day="Monday")

    assert len(client.get("/api/predictions", headers=two_users["alice_h"]).json()) == 1
    assert len(client.get("/api/predictions", headers=two_users["bob_h"]).json()) == 2


def test_user_id_cannot_be_spoofed_via_request_body(client, two_users):
    """BOLA-09: ``user_id`` di body diabaikan; kepemilikan selalu dari token."""
    response = client.post(
        "/api/history",
        headers=two_users["bob_h"],
        json={
            "visit_date": "2025-07-01",
            "visit_day": "Friday",
            "visitor_total": 800,
            "user_id": 1,  # percobaan memalsukan pemilik
        },
    )
    assert response.status_code == 201
    created = response.json()

    # Record harus tetap milik Bob, bukan user_id=1 yang dipalsukan.
    assert created["user_id"] == client.get("/auth/me", headers=two_users["bob_h"]).json()["id"]


# ------------------------------------------------------------------------------
# Akses tanpa autentikasi
# ------------------------------------------------------------------------------


def test_all_crud_endpoints_require_authentication(client):
    """Semua endpoint resource menolak request tanpa token dengan 401."""
    checks = [
        ("get", "/api/history", None),
        ("post", "/api/history", {"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 10}),
        ("get", "/api/history/1", None),
        ("put", "/api/history/1", {"visitor_total": 1}),
        ("delete", "/api/history/1", None),
        ("post", "/api/predict", {"visit_day": "Sunday"}),
        ("get", "/api/predictions", None),
        ("get", "/api/predictions/1", None),
        ("delete", "/api/predictions/1", None),
    ]
    for method, url, body in checks:
        kwargs = {"json": body} if body is not None else {}
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {url} -> {response.status_code}"
