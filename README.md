# PTM-06 — Implementasi Backend API, Validasi Masukan, Autentikasi JWT, dan Keamanan OWASP API

**Penerapan Algoritma XGBoost dengan Optimasi Grid Search untuk Prediksi Jumlah Pengunjung Berdasarkan Hari Kunjungan pada Wisata Religi Makam Gus Dur**

| Komponen | Keterangan |
|----------|------------|
| Mata Kuliah | Intelligent Mobile and Web Application Development |
| Kode / SKS | TIF-IMWAD / 3 SKS |
| Program Studi | Teknik Informatika |
| Pertemuan | 06 dari 16 |
| Semester / T.A. | Ganjil 2025/2026 |
| Dosen Pengampu | Edwin Hari Agus Prastyo, S.Kom., M.Kom. |
| Platform | Website |
| Algoritma | XGBoost (regresi) |
| Optimasi | Grid Search |
| Stack Backend | FastAPI + SQLAlchemy + SQLite + python-jose + bcrypt |

---

## 1. Deskripsi Singkat

Repositori ini berisi hasil Tugas Mandiri PTM-06, yaitu **implementasi backend
API** untuk sistem prediksi jumlah pengunjung Wisata Religi Makam Gus Dur.
Implementasi mengacu pada kontrak yang telah disusun pada pertemuan sebelumnya:

- **PTM-03** — user story, use case, acceptance criteria
- **PTM-04** — High-Level Design dan Low-Level Design awal
- **PTM-05** — `openapi.yaml`, `models.py`, dan `erd.md`

Fokus pekerjaan PTM-06:

1. Arsitektur backend modular tiga lapisan (**Router → Service → Repository**).
2. Autentikasi & otorisasi stateless berbasis **JWT** (OAuth2 Password Flow,
   token pair, hashing password bcrypt).
3. Audit keamanan **OWASP API Security Top 10 (2023)** dan penutupan celah
   **Broken Object Level Authorization (BOLA)**.
4. Sanitasi masukan inferensi AI (prompt injection, validasi unggahan berkas).
5. Pengujian fungsional API dan **Postman Collection** yang dapat diimpor ulang.

---

## 2. Keterkaitan dengan Tugas Sebelumnya

| Pertemuan | Repositori | Kontribusi |
|-----------|------------|------------|
| PTM-03 | https://github.com/nnafisaaa/praktikum-promot-3 | Kebutuhan fungsional (FR-01..FR-08), user story, acceptance criteria |
| PTM-04 | https://github.com/nnafisaaa/tugas-4-promt | Arsitektur HLD, modul LLD awal, spesifikasi `POST /api/predict` |
| PTM-05 | https://github.com/nnafisaaa/tugas-5-prom | Kontrak `openapi.yaml`, skema `models.py`, ERD |

**Penelusuran kebutuhan ke implementasi:**

```text
FR-01/02  Input & validasi hari kunjungan   -> POST /api/history + validasi Pydantic
FR-03/04  Prediksi XGBoost & Grid Search     -> POST /api/predict, /api/predict/batch
FR-05     Menampilkan hasil prediksi         -> GET /api/predictions
FR-06     Informasi kegagalan                -> Handler galat 4xx/5xx terstandar
FR-07     Status proses                      -> GET /health (model_loaded)
FR-08     Retry/fallback                     -> POST /auth/refresh + retry di klien
```

**Penyesuaian sadar terhadap ERD PTM-05.** ERD PTM-05 belum memuat entitas
pengguna karena autentikasi belum dirancang pada pertemuan tersebut. Untuk
menerapkan otorisasi tingkat objek, ditambahkan:

- tabel **`users`** sebagai pemilik data;
- kolom **`user_id`** pada `visitor_history` dan `prediction_result`.

Relasi `VisitorHistory (1) — (N) PredictionResult` dari ERD PTM-05 tetap utuh.
Penyesuaian ini didokumentasikan sebagai `[ASUMSI-06]` dan `[ASUMSI-07]` pada
`docs/prompt-log/ptm-06-prompt-log.md`.

---

## 3. Struktur Repositori

```text
.
├── .env.example                      # Templat environment variable (tanpa secret riil)
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py             # Konfigurasi dari .env (pydantic-settings)
│   │   │   ├── database.py           # Engine, session factory, get_db
│   │   │   └── security.py           # bcrypt, JWT, sanitasi AI, validasi unggahan
│   │   ├── repositories/
│   │   │   └── __init__.py           # HANYA query basis data
│   │   ├── routers/
│   │   │   ├── auth.py               # /auth/signup, login, refresh, me
│   │   │   ├── history.py            # CRUD /api/history
│   │   │   ├── predictions.py        # /api/predict, /api/predictions
│   │   │   └── ai_inference.py       # /api/ai/infer (unggahan tersanitasi)
│   │   ├── services/
│   │   │   ├── auth_service.py       # Aturan bisnis autentikasi
│   │   │   ├── history_service.py    # Aturan bisnis + anti-BOLA
│   │   │   └── prediction_service.py # Inferensi AI + anti-BOLA
│   │   ├── dependencies.py           # get_current_user (protected route)
│   │   ├── models.py                 # Model ORM + schema Pydantic
│   │   └── main.py                   # Entrypoint FastAPI
│   ├── tests/                        # 59 pengujian otomatis (pytest)
│   ├── init_db.py                    # Bootstrap DB + akun demo
│   ├── verify_e2e.py                 # 54 pemeriksaan end-to-end
│   ├── openapi.json                  # Spesifikasi OpenAPI 3.1 hasil generate
│   ├── pytest.ini
│   └── requirements.txt
├── docs/
│   ├── postman/
│   │   └── postman-collection.json   # Koleksi uji (37 request, happy + error)
│   ├── prompt-log/
│   │   └── ptm-06-prompt-log.md      # Log prompt + iterasi + asumsi (WAJIB)
│   └── security/
│       └── owasp-audit.md            # Laporan audit OWASP + kode patch
└── README.md
```

---

## 4. Cara Menjalankan

### 4.1 Prasyarat

- Python 3.11 atau lebih baru
- pip
- Postman (opsional, untuk mengimpor koleksi uji)

### 4.2 Instalasi

```bash
# 1. Masuk ke direktori backend
cd backend

# 2. Buat dan aktifkan virtual environment
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

# 3. Pasang dependensi
pip install -r ../requirements.txt

# 4. Siapkan environment variable
cp ../.env.example .env      # Windows: Copy-Item ..\.env.example .env
```

### 4.3 Konfigurasi Wajib

Ubah `SECRET_KEY` pada `.env` sebelum menjalankan. Bangkitkan nilai acak:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 4.4 Inisialisasi Basis Data & Akun Demo

```bash
python init_db.py
```

Perintah ini membuat tabel dan akun demonstrasi:

```text
Email    : demo@example.com
Password : Demo12345
```

### 4.5 Menjalankan Server

```bash
uvicorn app.main:app --reload --port 8000
```

| Tautan | Keterangan |
|--------|------------|
| http://127.0.0.1:8000/docs | Dokumentasi interaktif (Swagger UI) |
| http://127.0.0.1:8000/redoc | Dokumentasi alternatif |
| http://127.0.0.1:8000/health | Health check + status model AI |
| http://127.0.0.1:8000/openapi.json | Spesifikasi OpenAPI mentah |

---

## 5. Daftar Endpoint

Legenda lapisan: **R** = Router, **S** = Service, **P** = Repository.
Tanda ★ menandai endpoint fitur AI.

| No | Endpoint | Method | R | S | P | Proteksi | Anti-BOLA |
|----|----------|--------|---|---|---|----------|-----------|
| 1 | `/auth/signup` | POST | ✅ | ✅ | ✅ | — | — |
| 2 | `/auth/login` | POST | ✅ | ✅ | ✅ | — | — |
| 3 | `/auth/refresh` | POST | ✅ | ✅ | ✅ | Refresh token | — |
| 4 | `/auth/me` | GET | ✅ | — | ✅ | Bearer JWT | — |
| 5 | `/api/history` | GET | ✅ | ✅ | ✅ | Bearer JWT | Filter `user_id` |
| 6 | `/api/history` | POST | ✅ | ✅ | ✅ | Bearer JWT | `user_id` dari token |
| 7 | `/api/history/{id}` | GET | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 |
| 8 | `/api/history/{id}` | PUT | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 |
| 9 | `/api/history/{id}` | DELETE | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 |
| 10 | ★ `/api/predict` | POST | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 (referensi) |
| 11 | ★ `/api/predict/batch` | POST | ✅ | ✅ | ✅ | Bearer JWT | ✅ maks. 7 item |
| 12 | `/api/predictions` | GET | ✅ | ✅ | ✅ | Bearer JWT | Filter `user_id` |
| 13 | `/api/predictions/{id}` | GET | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 |
| 14 | `/api/predictions/{id}` | DELETE | ✅ | ✅ | ✅ | Bearer JWT | ✅ 403 |
| 15 | ★ `/api/ai/infer` | POST | ✅ | ✅ | ✅ | Bearer JWT | MIME + magic bytes |

### Endpoint Inferensi AI ★ — Mekanisme Validasi & Sanitasi

`POST /api/predict` dan `POST /api/ai/infer` menerima masukan yang disanitasi
sebelum diproses oleh model:

1. **Normalisasi unicode (NFKC)** — menyeragamkan karakter yang tampak setara.
2. **Pembuangan karakter kontrol** — kecuali tab dan baris baru.
3. **Penetralan pola prompt injection** — frasa seperti *"ignore all previous
   instructions"*, `system:`, `<script>`, `${...}` diganti `[FILTERED]`.
4. **Pembatasan panjang** — maksimal 512 karakter untuk teks bebas.
5. **Validasi unggahan berlapis** (untuk `/api/ai/infer`):
   - ukuran berkas ≤ 5 MB (`413` bila dilampaui);
   - MIME whitelist hanya `image/jpeg` dan `image/png` (`415` bila tidak sesuai);
   - penolakan ekstensi berbahaya (`.php`, `.exe`, `.sh`, `.svg`, dan sejenisnya);
   - verifikasi **magic bytes** untuk mencegah pemalsuan MIME.

---

## 6. Contoh Penggunaan

### 6.1 Registrasi dan Login

```bash
# Registrasi
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"name":"Pengelola","email":"pengelola@example.com","password":"Rahasia123"}'

# Login
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"pengelola@example.com","password":"Rahasia123"}'
```

Simpan `access_token` dari respons, lalu gunakan sebagai Bearer token.

### 6.2 Profil Terproteksi

```bash
curl http://127.0.0.1:8000/auth/me -H "Authorization: Bearer <access_token>"
```

### 6.3 Prediksi Jumlah Pengunjung

```bash
curl -X POST http://127.0.0.1:8000/api/predict \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"visit_day":"Sunday"}'
```

Contoh respons (sesuai kontrak PTM-05, dengan field tambahan):

```json
{
  "status": "success",
  "prediction": 3100,
  "visit_day": "Sunday",
  "record_id": 1,
  "model_source": "baseline",
  "created_at": "2026-10-09T10:00:00Z"
}
```

> **Catatan `model_source`.** Bila artefak model XGBoost tersedia pada
> `MODEL_PATH`, nilainya `"xgboost"`. Bila tidak tersedia, service memakai
> baseline deterministik dan melaporkan `"baseline"` secara jujur — sistem
> tidak mengarang hasil seolah-olah berasal dari model.

### 6.4 Refresh Token

```bash
curl -X POST http://127.0.0.1:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

---

## 7. Pengujian

### 7.1 Pengujian Otomatis

```bash
cd backend
pytest
```

Hasil: **59 pengujian lulus**, mencakup autentikasi JWT, isolasi kepemilikan
objek (BOLA), validasi masukan, batas sumber daya, sanitasi teks AI, dan
validasi unggahan berkas.

### 7.2 Verifikasi End-to-End

Jalankan server terlebih dahulu, lalu:

```bash
cd backend
python verify_e2e.py
```

Hasil: **54 pemeriksaan lulus**. Skrip ini menyerang endpoint dengan skenario
nyata, termasuk 8 percobaan akses lintas pengguna (BOLA) yang seluruhnya
ditolak dengan HTTP 403.

### 7.3 Postman Collection

1. Impor `docs/postman/postman-collection.json` ke Postman.
2. Jalankan folder **01 - Authentication** lebih dulu; token tersimpan otomatis.
3. Untuk membuktikan celah BOLA tertutup, jalankan folder
   **06 - BOLA Security** — semua request di sana harus mengembalikan **403**.
4. Alternatif: gunakan Collection Runner untuk menjalankan seluruh folder.

Koleksi terdiri atas **37 request** dalam 7 folder, mencakup alur sukses
(`200`/`201`/`204`) dan alur kegagalan (`401`/`403`/`404`/`409`/`413`/`415`/`422`).

---

## 8. Ringkasan Keamanan

| Kategori OWASP (2023) | Kontrol yang Diterapkan | Bukti |
|-----------------------|-------------------------|-------|
| API1:2023 BOLA | `get_owned()` di service + filter `user_id` di repository | 8 serangan → 403 |
| API2:2023 Broken Authentication | bcrypt + salt, token pair, pemisahan tipe token, 401 seragam | 7 skenario lulus |
| API3:2023 Mass Assignment | `user_id` hanya dari token, tidak ada di schema masukan | Spoofing gagal |
| API4:2023 Resource Consumption | Berkas ≤5 MB, batch ≤7, `limit` dijepit ≤500 | 413/422 sesuai |
| API8:2023 Misconfiguration | Semua secret dari `.env`, CORS terbatas, galat tanpa stack trace | `.env.example` |
| API10:2023 Unsafe Consumption | MIME whitelist + verifikasi magic bytes | 415 pada spoofing |
| Prompt Injection | `sanitize_ai_text()` menetralkan pola injeksi | `[FILTERED]` |

Laporan audit lengkap, termasuk kode patch dan status verifikasi setiap temuan,
tersedia pada [`docs/security/owasp-audit.md`](docs/security/owasp-audit.md).

---

## 9. Deliverable PTM-06

| Artefak | Lokasi | Status |
|---------|--------|--------|
| Source code backend modular | `backend/app/` | ✅ |
| `.env.example` | `./.env.example` | ✅ |
| Postman collection | `docs/postman/postman-collection.json` | ✅ |
| Laporan audit OWASP | `docs/security/owasp-audit.md` | ✅ |
| Prompt log | `docs/prompt-log/ptm-06-prompt-log.md` | ✅ |
| Pengujian otomatis | `backend/tests/` | ✅ 59 lulus |
| Verifikasi end-to-end | `backend/verify_e2e.py` | ✅ 54 lulus |
| Spesifikasi OpenAPI | `backend/openapi.json` | ✅ |

---

## 10. Batasan yang Diketahui

Dinyatakan secara terbuka agar tidak menimbulkan kesan berlebihan:

1. **Refresh token belum dirotasi atau di-revoke** — hanya divalidasi tanda
   tangan dan masa berlakunya. Rotasi token berada di luar cakupan PTM-06.
2. **Rate limiting per klien belum diterapkan** — pembatasan saat ini bersifat
   struktural (ukuran berkas, jumlah item, jumlah baris).
3. **SQLite untuk pengembangan** — produksi sebaiknya memakai PostgreSQL
   dengan hak akses basis data yang dibatasi.
4. **Mode baseline saat artefak model tidak tersedia** — dilaporkan secara
   jujur melalui field `model_source`.
5. **Verifikasi melalui pengujian terprogram** — pengujian penetrasi independen
   tetap disarankan sebelum peluncuran produksi.

---

## 11. Anggota Tim

| No | Nama | NIM |
|----|------|-----|
| 1 | Uswatun Nafisah | 2395114070 |


**Nama folder submisi:** `2395114070_PTM06_IMWAD`

---

## 12. Pesan Commit Wajib

```text
feat(backend): implement JWT auth, CRUD endpoints, OWASP patches [PTM-06]
```

---

## 13. Referensi

- OWASP API Security Top 10 2023 — https://owasp.org/API-Security/
- FastAPI Security Tutorial — https://fastapi.tiangolo.com/tutorial/security/
- python-jose Documentation — https://python-jose.readthedocs.io/
- SQLAlchemy 2.0 Documentation — https://docs.sqlalchemy.org/
- Pydantic Settings — https://docs.pydantic.dev/latest/concepts/pydantic_settings/

---

*Praktikum Tugas Mandiri PTM-06 — Backend API & Security | IMWAD*
