"""Skrip verifikasi end-to-end terhadap server yang benar-benar berjalan.

Dijalankan setelah ``uvicorn`` hidup. Skrip ini melakukan alur lengkap seperti
pengguna nyata melalui HTTP: signup -> login -> refresh -> protected route ->
CRUD -> prediksi AI -> unggahan -> pengujian celah BOLA lintas pengguna.

Jalankan:
    python verify_e2e.py [base_url]
"""

from __future__ import annotations

import io
import sys

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    """Catat hasil satu pemeriksaan."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {label}")
    else:
        failed += 1
        print(f"  [FAIL] {label} :: {detail}")


def main() -> int:
    """Jalankan seluruh skenario verifikasi."""
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    print("\n== 1. Health & dokumentasi ==")
    r = client.get("/health")
    check("GET /health -> 200", r.status_code == 200, r.text)
    check("model_loaded terlaporkan", "model_loaded" in r.json(), r.text)
    check("GET /docs -> 200", client.get("/docs").status_code == 200)
    check("GET /openapi.json -> 200", client.get("/openapi.json").status_code == 200)

    print("\n== 2. Autentikasi (signup, login, refresh) ==")
    r = client.post(
        "/auth/signup",
        json={"name": "Pengelola A", "email": "pengelola.a@example.com", "password": "Rahasia123"},
    )
    check("POST /auth/signup -> 201", r.status_code == 201, r.text)
    tokens_a = r.json()
    check("access_token diterima", bool(tokens_a.get("access_token")))
    check("refresh_token diterima", bool(tokens_a.get("refresh_token")))

    r = client.post(
        "/auth/signup",
        json={"name": "Pengelola A", "email": "pengelola.a@example.com", "password": "Rahasia123"},
    )
    check("signup email duplikat -> 409", r.status_code == 409, r.text)

    r = client.post(
        "/auth/login",
        json={"email": "pengelola.a@example.com", "password": "Rahasia123"},
    )
    check("POST /auth/login -> 200", r.status_code == 200, r.text)
    tokens_a = r.json()

    r = client.post(
        "/auth/login",
        json={"email": "pengelola.a@example.com", "password": "PasswordSalah9"},
    )
    check("login password salah -> 401", r.status_code == 401, r.text)

    r = client.post("/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]})
    check("POST /auth/refresh -> 200", r.status_code == 200, r.text)
    refreshed = r.json()

    r = client.post("/auth/refresh", json={"refresh_token": tokens_a["access_token"]})
    check("refresh memakai access token -> 401", r.status_code == 401, r.text)

    headers_a = {"Authorization": f"Bearer {tokens_a['access_token']}"}
    r = client.get("/auth/me", headers=headers_a)
    check("GET /auth/me (token valid) -> 200", r.status_code == 200, r.text)
    check("profil tanpa password hash", "hashed_password" not in r.text, r.text)

    r = client.get("/auth/me")
    check("GET /auth/me (tanpa token) -> 401", r.status_code == 401, r.text)

    r = client.get("/auth/me", headers={"Authorization": "Bearer token.palsu.xyz"})
    check("GET /auth/me (token palsu) -> 401", r.status_code == 401, r.text)

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {refreshed['access_token']}"})
    check("access token hasil refresh valid", r.status_code == 200, r.text)

    print("\n== 3. CRUD histori pengunjung ==")
    r = client.post(
        "/api/history",
        headers=headers_a,
        json={"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500},
    )
    check("POST /api/history -> 201", r.status_code == 201, r.text)
    history_a = r.json()

    r = client.post(
        "/api/history",
        headers=headers_a,
        json={"visit_date": "2025-06-01", "visit_day": "Sunday", "visitor_total": 1500},
    )
    check("histori tanggal duplikat -> 409", r.status_code == 409, r.text)

    r = client.post(
        "/api/history",
        headers=headers_a,
        json={"visit_date": "01-06-2025", "visit_day": "Sunday", "visitor_total": 1500},
    )
    check("format tanggal salah -> 422", r.status_code == 422, r.text)

    r = client.get(f"/api/history/{history_a['id']}", headers=headers_a)
    check("GET /api/history/{id} -> 200", r.status_code == 200, r.text)

    r = client.put(
        f"/api/history/{history_a['id']}", headers=headers_a, json={"visitor_total": 1750}
    )
    check("PUT /api/history/{id} -> 200", r.status_code == 200, r.text)
    check("nilai ter-update", r.json().get("visitor_total") == 1750, r.text)

    r = client.get("/api/history", headers=headers_a)
    check("GET /api/history -> 200", r.status_code == 200, r.text)
    check("daftar memuat 1 catatan", len(r.json()) == 1, r.text)

    r = client.get("/api/history/999999", headers=headers_a)
    check("histori tidak ada -> 404 (bukan 500)", r.status_code == 404, r.text)

    print("\n== 4. Prediksi AI & CRUD prediksi ==")
    r = client.post("/api/predict", headers=headers_a, json={"visit_day": "Sunday"})
    check("POST /api/predict -> 200", r.status_code == 200, r.text)
    pred_a = r.json()
    check("status success", pred_a.get("status") == "success", r.text)
    check("prediction berupa integer", isinstance(pred_a.get("prediction"), int), r.text)

    r = client.post("/api/predict", headers=headers_a, json={"visit_day": "HariLibur"})
    check("hari tidak valid -> 422", r.status_code == 422, r.text)

    r = client.post(
        "/api/predict/batch", headers=headers_a, json={"visit_days": ["Monday", "Friday"]}
    )
    check("POST /api/predict/batch -> 200", r.status_code == 200, r.text)
    check("batch mengembalikan 2 hasil", len(r.json()) == 2, r.text)

    r = client.post(
        "/api/predict/batch", headers=headers_a, json={"visit_days": ["Monday"] * 9}
    )
    check("batch > 7 item -> 422", r.status_code == 422, r.text)

    r = client.get("/api/predictions", headers=headers_a)
    check("GET /api/predictions -> 200", r.status_code == 200, r.text)
    check("daftar prediksi memuat 3", len(r.json()) == 3, r.text)

    r = client.get(f"/api/predictions/{pred_a['record_id']}", headers=headers_a)
    check("GET /api/predictions/{id} -> 200", r.status_code == 200, r.text)

    print("\n== 5. Inferensi AI dari unggahan berkas ==")
    r = client.post(
        "/api/ai/infer",
        headers=headers_a,
        files={"file": ("pengunjung.png", io.BytesIO(PNG_1PX), "image/png")},
        data={"visit_day": "Sunday"},
    )
    check("upload PNG valid -> 200", r.status_code == 200, r.text)
    if r.status_code == 200:
        check("mime_type dilaporkan", r.json().get("mime_type") == "image/png", r.text)

    r = client.post(
        "/api/ai/infer",
        headers=headers_a,
        files={"file": ("jahat.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-msdownload")},
        data={"visit_day": "Sunday"},
    )
    check("MIME tidak diizinkan -> 415", r.status_code == 415, r.text)

    r = client.post(
        "/api/ai/infer",
        headers=headers_a,
        files={"file": ("palsu.png", io.BytesIO(b"<?php system($_GET['c']); ?>"), "image/png")},
        data={"visit_day": "Sunday"},
    )
    check("MIME spoofing (isi bukan PNG) -> 415", r.status_code == 415, r.text)

    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 2048)
    r = client.post(
        "/api/ai/infer",
        headers=headers_a,
        files={"file": ("besar.png", io.BytesIO(oversized), "image/png")},
        data={"visit_day": "Sunday"},
    )
    check("berkas > 5MB -> 413", r.status_code == 413, r.text)

    r = client.post(
        "/api/ai/infer",
        files={"file": ("pengunjung.png", io.BytesIO(PNG_1PX), "image/png")},
        data={"visit_day": "Sunday"},
    )
    check("upload tanpa token -> 401", r.status_code == 401, r.text)

    print("\n== 6. Celah BOLA lintas pengguna (OWASP API1:2023) ==")
    r = client.post(
        "/auth/signup",
        json={"name": "Pengelola B", "email": "pengelola.b@example.com", "password": "Rahasia456"},
    )
    check("signup pengguna B -> 201", r.status_code == 201, r.text)
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.get(f"/api/history/{history_a['id']}", headers=headers_b)
    check("B membaca histori A -> 403", r.status_code == 403, r.text)

    r = client.put(
        f"/api/history/{history_a['id']}", headers=headers_b, json={"visitor_total": 1}
    )
    check("B mengubah histori A -> 403", r.status_code == 403, r.text)

    r = client.get(f"/api/history/{history_a['id']}", headers=headers_a)
    check("data A tidak berubah setelah percobaan B", r.json()["visitor_total"] == 1750, r.text)

    r = client.delete(f"/api/history/{history_a['id']}", headers=headers_b)
    check("B menghapus histori A -> 403", r.status_code == 403, r.text)

    r = client.post(
        "/api/predict",
        headers=headers_b,
        json={"visit_day": "Sunday", "visitor_history_id": history_a["id"]},
    )
    check("B memakai histori A untuk prediksi -> 403", r.status_code == 403, r.text)

    r = client.get(f"/api/predictions/{pred_a['record_id']}", headers=headers_b)
    check("B membaca prediksi A -> 403", r.status_code == 403, r.text)

    r = client.delete(f"/api/predictions/{pred_a['record_id']}", headers=headers_b)
    check("B menghapus prediksi A -> 403", r.status_code == 403, r.text)

    r = client.get("/api/history", headers=headers_b)
    check("daftar histori B kosong (terisolasi)", len(r.json()) == 0, r.text)

    r = client.get("/api/predictions", headers=headers_b)
    check("daftar prediksi B kosong (terisolasi)", len(r.json()) == 0, r.text)

    print("\n== 7. Pembersihan (happy path delete) ==")
    r = client.delete(f"/api/history/{history_a['id']}", headers=headers_a)
    check("A menghapus histori sendiri -> 204", r.status_code == 204, r.text)

    r = client.delete(f"/api/predictions/{pred_a['record_id']}", headers=headers_a)
    check("A menghapus prediksi sendiri -> 204", r.status_code == 204, r.text)

    client.close()

    print("\n" + "=" * 62)
    print(f"HASIL: {passed} pemeriksaan PASS, {failed} pemeriksaan FAIL")
    print("=" * 62)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
