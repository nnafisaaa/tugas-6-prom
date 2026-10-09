"""Pengujian CRUD histori pengunjung: alur sukses dan validasi."""

from __future__ import annotations

import pytest

from tests.conftest import auth_header, signup_user


@pytest.fixture
def user_header(client):
    tokens = signup_user(client, name="Nafisa", email="crud@example.com")
    return auth_header(tokens)


def test_create_history_success(client, user_header):
    response = client.post(
        "/api/history",
        headers=user_header,
        json={"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["visit_date"] == "2025-06-01"
    assert body["visit_day"] == "Sunday"
    assert body["visitor_total"] == 1500


def test_create_history_rejects_duplicate_date_with_409(client, user_header):
    payload = {"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500}
    assert client.post("/api/history", headers=user_header, json=payload).status_code == 201
    assert client.post("/api/history", headers=user_header, json=payload).status_code == 409


@pytest.mark.parametrize(
    "bad_payload",
    [
        {"visit_date": "01-06-2025", "visit_day": "Sunday", "visitor_total": 10},
        {"visit_date": "2025-06-01", "visit_day": "HariLibur", "visitor_total": 10},
        {"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": -5},
        {"visit_date": "2025-06-01", "visit_day": "Sunday"},
    ],
)
def test_create_history_validation_returns_422(client, user_header, bad_payload):
    response = client.post("/api/history", headers=user_header, json=bad_payload)
    assert response.status_code == 422


def test_update_history_success(client, user_header):
    created = client.post(
        "/api/history",
        headers=user_header,
        json={"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500},
    ).json()

    response = client.put(
        f"/api/history/{created['id']}",
        headers=user_header,
        json={"visitor_total": 2000},
    )
    assert response.status_code == 200
    assert response.json()["visitor_total"] == 2000
    # Field lain tidak berubah.
    assert response.json()["visit_day"] == "Sunday"


def test_delete_history_success(client, user_header):
    created = client.post(
        "/api/history",
        headers=user_header,
        json={"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500},
    ).json()

    assert client.delete(f"/api/history/{created['id']}", headers=user_header).status_code == 204
    assert client.get(f"/api/history/{created['id']}", headers=user_header).status_code == 404


def test_delete_nonexistent_history_returns_404(client, user_header):
    assert client.delete("/api/history/999999", headers=user_header).status_code == 404


def test_predictions_are_persisted_and_listed(client, user_header):
    client.post("/api/predict", headers=user_header, json={"visit_day": "Sunday"})
    client.post("/api/predict", headers=user_header, json={"visit_day": "Saturday"})

    listed = client.get("/api/predictions", headers=user_header).json()
    assert len(listed) == 2
    days = {item["visit_day"] for item in listed}
    assert days == {"Sunday", "Saturday"}


def test_delete_prediction_success(client, user_header):
    created = client.post("/api/predict", headers=user_header, json={"visit_day": "Sunday"}).json()

    assert client.delete(
        f"/api/predictions/{created['record_id']}", headers=user_header
    ).status_code == 204
    assert client.get(
        f"/api/predictions/{created['record_id']}", headers=user_header
    ).status_code == 404


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "model_loaded" in body
