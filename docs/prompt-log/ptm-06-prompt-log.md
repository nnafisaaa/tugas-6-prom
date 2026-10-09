# PTM-06 Prompt Log — Implementasi Backend API, Autentikasi JWT, dan Keamanan OWASP API

**Proyek:** Sistem Prediksi Jumlah Pengunjung Wisata Religi Makam Gus Dur
**Pertemuan:** 06 dari 16
**Mata Kuliah:** Intelligent Mobile and Web Application Development (TIF-IMWAD)
**Dosen Pengampu:** Edwin Hari Agus Prastyo, S.Kom., M.Kom.
**Semester / T.A.:** Ganjil 2025/2026
**Kode Artefak:** `ptm-06-prompt-log`

---

## 1. Tujuan dan Ruang Lingkup

Dokumen ini mencatat penggunaan AI sebagai alat bantu pada praktikum PTM-06,
yang mencakup:

1. Scaffold arsitektur backend modular tiga lapisan (Router → Service → Repository).
2. Implementasi autentikasi JWT (OAuth2 Password Flow, token pair, bcrypt).
3. Audit keamanan OWASP API Security Top 10 (2023) dan patch celah BOLA.
4. Sanitasi masukan inferensi AI dan pembatasan sumber daya.
5. Pengujian fungsional API dan penyusunan Postman Collection.

Sesuai ketentuan praktikum, setiap hasil AI diperlakukan sebagai **draf awal**
yang wajib melalui pemeriksaan manual. Bagian yang bergantung pada keputusan
yang belum tersedia ditandai `[ASUMSI-XX]` untuk diverifikasi tim.

---

## 2. Konteks Proyek (Keterkaitan dengan Pertemuan Sebelumnya)

| Pertemuan | Artefak | Kontribusi pada backend PTM-06 |
|-----------|---------|-------------------------------|
| PTM-03 | `user-stories.md`, `prompt-log.md` | Sumber ID user story (US-01..US-08) dan acceptance criteria (AC-01.1..AC-08.2) yang dipetakan ke endpoint |
| PTM-04 | `hld.md`, `lld-awal.md` | Arsitektur client-server, daftar modul (Validation, Prediction, Model Service, Grid Search, Result, Error Handling), spesifikasi `POST /api/predict` |
| PTM-05 | `openapi.yaml`, `models.py`, `erd.md` | Kontrak endpoint, skema Pydantic, dan ERD yang menjadi basis implementasi |

**Penelusuran kebutuhan.** Setiap endpoint yang diimplementasikan pada PTM-06
dapat ditelusuri ke artefak sebelumnya:

```text
FR-01/02 (input & validasi)      -> POST /api/history, validasi Pydantic
FR-03/04 (XGBoost & Grid Search) -> POST /api/predict, POST /api/predict/batch
FR-05    (tampilkan hasil)       -> GET /api/predictions
FR-06    (informasi kegagalan)   -> Handler galat 4xx/5xx terstandar
FR-07    (status proses)         -> GET /health (model_loaded)
FR-08    (retry/fallback)        -> POST /auth/refresh, retry di sisi klien
```

**Penyesuaian terhadap PTM-05.** ERD PTM-05 belum memuat entitas pengguna
karena autentikasi belum dirancang pada pertemuan tersebut. Dua penyesuaian
diperlukan agar sistem dapat menerapkan otorisasi tingkat objek:

| Penyesuaian | Alasan | Asumsi |
|-------------|--------|--------|
| Tabel `users` ditambahkan | Autentikasi JWT memerlukan identitas pemilik data | `[ASUMSI-06]` |
| Kolom `user_id` pada `visitor_history` & `prediction_result` | Prasyarat verifikasi kepemilikan objek (anti-BOLA) | `[ASUMSI-07]` |

Relasi `VisitorHistory (1) — (N) PredictionResult` dari ERD PTM-05 tetap
dipertahankan tanpa perubahan.

---

## 3. Log Prompt

### 3.1 Sesi 1 — D.1: Scaffold Arsitektur Modular

**Target:** menghasilkan struktur Router → Service → Repository.

**Prompt yang dijalankan** (mengikuti Prompt D.1 pada LKP, dengan `<...>` diisi konteks proyek):

```text
[Peran]   Kamu adalah backend engineer senior ahli FastAPI / Next.js API Routes.
[Tugas]   Generate scaffold struktur folder modular (Router → Service → Repository)
          berdasarkan spesifikasi OpenAPI berikut.
[Konteks] OpenAPI : <openapi.yaml PTM-05 — POST /api/predict>
          Stack   : FastAPI
          DB      : SQLite + SQLAlchemy
[Format output]
  1) Struktur folder lengkap (routers/, services/, repositories/, models/, core/).
  2) Boilerplate kode tiap lapisan untuk 1 resource contoh (/users).
  3) Konfigurasi koneksi DB (SQLAlchemy session generator).
  4) Template .env.example: DATABASE_URL, SECRET_KEY, ALGORITHM,
     ACCESS_TOKEN_EXPIRE_MINUTES, MODEL_PATH, SCALER_PATH, MAX_FILE_SIZE_MB.
[Aturan]
  - Pisahkan lapisan secara ketat; tidak ada logika bisnis langsung di router.
  - Repository hanya mengurus query DB; Service menangani validasi bisnis & inferensi.
  - Semua konfigurasi sensitif wajib lewat env, DILARANG KERAS di-hardcode.
```

**Output AI (draf awal).**

Struktur yang diusulkan:

```text
backend/
├── app/
│   ├── core/          (config.py, database.py, security.py)
│   ├── models/        (models.py)
│   ├── repositories/  (query DB)
│   ├── routers/       (endpoint HTTP)
│   ├── services/      (aturan bisnis)
│   └── main.py
├── .env.example
└── requirements.txt
```

Boilerplate untuk resource `/users`, session generator SQLAlchemy dengan
`try/finally`, dan `.env.example`.

**Koreksi manual yang dilakukan tim.**

| # | Masalah pada Output AI Pertama | Revisi yang Diterapkan |
|---|--------------------------------|------------------------|
| 1 | AI memakai `models/` sebagai paket direktori, menyulitkan impor model ORM dan schema | Digabung menjadi satu modul `app/models.py` agar impor seragam |
| 2 | Session generator tanpa `try/finally` pada draf pertama | Ditambah `try/finally` + `pool_pre_ping=True` untuk cegah kebocoran koneksi |
| 3 | `.env.example` memuat nilai contoh yang terlihat seperti kredensial nyata | Diganti placeholder jelas + instruksi pembangkitan `SECRET_KEY` |
| 4 | Resource contoh `/users` tidak relevan dengan domain proyek | Diganti resource nyata: `visitor_history` dan `prediction_result` sesuai ERD PTM-05 |
| 5 | AI menaruh pengecekan kepemilikan di router | Dipindahkan ke lapisan service agar tidak dapat dilewati |

**Verifikasi tim.**

- Struktur direktori diperiksa memenuhi checklist D.1: `routers/`, `services/`,
  `repositories/`, `core/` terpisah tegas. ✅
- `get_db()` diverifikasi selalu menutup sesi melalui `try/finally`. ✅
- `.env.example` diperiksa tidak memuat kredensial riil. ✅

---

### 3.2 Sesi 2 — D.2: Autentikasi JWT & Password Hashing

**Target:** signup, login, refresh, dan protected route.

**Prompt yang dijalankan:**

```text
[Peran]   Kamu adalah backend security engineer ahli OAuth2 Password Flow dan JWT.
[Tugas]   Implementasikan autentikasi JWT lengkap pada stack FastAPI
          berdasarkan endpoint auth pada spesifikasi OpenAPI.
[Konteks] Endpoint auth : POST /auth/signup, POST /auth/login,
                          POST /auth/refresh, GET /auth/me
          Stack         : FastAPI + python-jose + passlib[bcrypt]
[Format output]
  1) Utility hash password bcrypt (hash_password dan verify_password).
  2) Generator token pair: Access Token (exp: 30 menit) + Refresh Token (exp: 7 hari).
  3) Dependency protected route (ekstraksi & validasi Bearer JWT token).
  4) Handler signup: validasi schema, cek duplikasi email, hashing, simpan.
  5) Handler login: verifikasi identitas, cek password hash, kembalikan token pair.
  6) Handler refresh: validasi refresh token, terbitkan access token baru.
  7) Protected endpoint GET /auth/me: kembalikan profil pengguna login.
[Aturan]
  - SECRET_KEY wajib dari environment variable. Password TIDAK BOLEH plaintext.
  - HTTP 401 jika token kadaluarsa/invalid; 403 jika otorisasi tidak memadai.
  - DILARANG menaruh informasi rahasia di dalam claims payload JWT.
```

**Output AI (draf awal).** Utility bcrypt, generator token pair, dependency
`get_current_user`, dan empat handler auth.

**Koreksi manual yang dilakukan tim.**

| # | Masalah pada Output AI Pertama | Revisi yang Diterapkan |
|---|--------------------------------|------------------------|
| 1 | Access token dan refresh token tidak dibedakan jenisnya — refresh token dapat dipakai sebagai access token dan sebaliknya | Ditambah klaim `type` (`"access"`/`"refresh"`) dan parameter `expected_type` pada `decode_token()` |
| 2 | Pesan galat login membedakan "email tidak ditemukan" vs "password salah" | Pesan disamakan menjadi "Email atau password salah" untuk mencegah enumerasi akun |
| 3 | AI memakai `passlib.CryptContext` saja | Verifikasi menemukan `passlib` 1.7.4 tidak kompatibel dengan `bcrypt` 5.x — galat "password cannot be longer than 72 bytes". Diganti pemanggilan `bcrypt` langsung dengan pemotongan eksplisit 72 byte |
| 4 | Validasi kekuatan password belum ada | Ditambah aturan minimal 8 karakter, wajib memuat huruf dan angka |
| 5 | Endpoint `/auth/me` mengembalikan objek ORM langsung | Diganti schema `UserPublic` tanpa `hashed_password` agar hash tidak bocor |
| 6 | `Authorization` skema selain Bearer tidak ditangani | `HTTPBearer(auto_error=False)` + pesan 401 seragam |

**Verifikasi tim.**

- Password di basis data diperiksa berawalan `$2b$` (hash bcrypt). ✅
- Claims JWT diperiksa tidak memuat `password`/`secret`. ✅
- `GET /auth/me` tanpa token, token palsu, dan skema Basic → semuanya 401. ✅
- Refresh dengan access token → 401 (pemisahan tipe bekerja). ✅

---

### 3.3 Sesi 3 — D.3: Audit OWASP & Patch BOLA

**Target:** temuan OWASP, patch anti-BOLA, sanitasi masukan AI.

**Prompt yang dijalankan:**

```text
[Peran]   Kamu adalah API Security Auditor berpengalaman standar
          OWASP API Security Top 10 (2023).
[Tugas]   Audit kode backend berikut terhadap kerentanan OWASP API dan
          berikan perbaikan konkret.
[Konteks] Kode yang diaudit : <router/service CRUD dan handler inferensi AI>
          Fokus utama       : API1:2023 BOLA/IDOR,
                              API2:2023 Broken Authentication,
                              API4:2023 Unrestricted Resource Consumption,
                              Sanitasi masukan inferensi AI
[Format output]
  1) Tabel Audit: | Endpoint | Kerentanan OWASP | Tingkat Risiko |
                   Kode Patch | Status Verifikasi |
  2) Kode patch konkret (minimal diff) untuk anti-BOLA.
  3) Middleware/helper sanitasi input AI: validasi ukuran file (<=5MB),
     MIME whitelisting, dan pembersihan string dari karakter injeksi.
[Aturan]
  - Pada operasi CRUD berparameter ID, WAJIB ada pengecekan:
    apakah data tersebut benar milik current_user.id?
    Jika tidak cocok, tolak HTTP 403 Forbidden.
  - Perbaikan bersifat presisi, tidak menulis ulang arsitektur secara berlebihan.
```

**Output AI (draf awal).** Tabel audit berisi 14 temuan, patch `get_owned()`,
dan helper sanitasi.

**Koreksi manual yang dilakukan tim.**

| # | Masalah pada Output AI Pertama | Revisi yang Diterapkan |
|---|--------------------------------|------------------------|
| 1 | AI hanya menambahkan pengecekan kepemilikan pada `GET` | Diperluas ke seluruh operasi: `PUT`, `DELETE`, dan referensi lintas-resource pada `POST /api/predict` |
| 2 | AI mengembalikan 404 untuk objek milik orang lain (menyembunyikan keberadaan) | Sesuai aturan prompt, diubah menjadi **403 Forbidden** agar sesuai ketentuan LKP |
| 3 | Filter kepemilikan hanya di service | Ditambah *defense in depth*: filter `user_id` juga dipasang pada query repository |
| 4 | Temuan mass assignment (`user_id` di body) belum teridentifikasi AI | Ditambahkan setelah tim menguji spoofing `user_id` secara manual; schema masukan dipastikan tidak memuat field tersebut |
| 5 | Sanitasi hanya membuang karakter kontrol | Ditambah normalisasi unicode NFKC dan penetralan pola prompt injection menjadi `[FILTERED]` |
| 6 | Validasi unggahan hanya memeriksa MIME header | Ditambah verifikasi **magic bytes** untuk mencegah MIME spoofing, dan daftar ekstensi terblokir |
| 7 | AI mengusulkan menulis ulang seluruh lapisan | Ditolak; patch dipertahankan sebagai *minimal diff* sesuai aturan prompt |
| 8 | Batas sumber daya hanya pada unggahan | Ditambah batas batch (maksimal 7) dan penjepitan `limit` (maksimal 500) |

**Verifikasi tim.** Lihat `docs/security/owasp-audit.md` — seluruh 8 serangan
BOLA dikembalikan 403, dan setiap patch memiliki bukti pengujian.

---

### 3.4 Sesi 4 — Iterasi Perbaikan Galat

Iterasi ini dijalankan setelah pengujian awal menemukan dua masalah nyata.

**Masalah 1 — Galat hash bcrypt.**

```text
Masalah : ValueError: password cannot be longer than 72 bytes
Penyebab: Ketidakcocokan passlib 1.7.4 dengan bcrypt 5.x.
Prompt  : Perbaiki masalah ini dengan patch minimal. Jangan ubah arsitektur.
Revisi  : hash_password()/verify_password() memakai modul bcrypt langsung
          dengan pemotongan eksplisit 72 byte (BCRYPT_MAX_BYTES).
Bukti   : 10 pengujian autentikasi kembali lulus.
```

**Masalah 2 — Format galat tidak seragam.**

```text
Masalah : Endpoint mengembalikan {"detail": ...} sedangkan handler kustom
          mengembalikan {"message": ...}, sehingga klien harus menangani
          dua bentuk respons galat.
Prompt  : Seragamkan format galat seluruh aplikasi tanpa mengubah perilaku
          status code.
Revisi  : Ditambah handler HTTPException yang memetakan galat ke
          {"status": "error", "message": ...}.
Bukti   : Pengujian "login email tidak dikenal" lulus dengan format seragam.
```

---

## 4. Tabel Iterasi Prompt (Ringkasan)

| Prompt | Masalah pada Output AI Pertama | Revisi / Prompt Lanjutan yang Digunakan |
|--------|-------------------------------|------------------------------------------|
| D.1 Scaffold Modular | Struktur `models/` sebagai direktori menyulitkan impor; resource contoh tidak relevan | "Gabungkan model ORM dan schema dalam satu modul `app/models.py`, dan ganti resource contoh dengan `visitor_history` serta `prediction_result` sesuai ERD PTM-05." |
| D.2 Autentikasi JWT | Refresh token dan access token tidak dibedakan; pesan login membocorkan keberadaan akun; galat bcrypt 72 byte | "Tambahkan klaim `type` pada JWT dan validasi jenis token saat decode. Samakan pesan galat login. Ganti passlib dengan pemanggilan bcrypt langsung yang memotong input pada 72 byte." |
| D.3 Audit OWASP & BOLA | Pengecekan kepemilikan hanya pada GET; mass assignment luput; sanitasi dangkal | "Terapkan verifikasi kepemilikan pada seluruh operasi berparameter ID dan pada referensi `visitor_history_id`. Tambahkan verifikasi magic bytes untuk unggahan dan normalisasi unicode pada sanitasi teks." |
| Iterasi lanjutan | Format galat tidak konsisten antar-endpoint | "Seragamkan seluruh galat menjadi `{status, message}` melalui handler HTTPException tanpa mengubah status code." |

---

## 5. Asumsi Teknis & Keputusan Desain — `[ASUMSI-XX]`

| Kode | Isi Asumsi / Keputusan Desain AI | Verifikasi Tim |
|------|----------------------------------|----------------|
| ASUMSI-01 | SQLite dipakai sebagai basis data pengembangan, PostgreSQL disiapkan untuk produksi melalui `DATABASE_URL` | **Diterapkan** — sesuai keputusan stack; PostgreSQL hanya perlu ganti `DATABASE_URL` |
| ASUMSI-02 | Artefak model XGBoost tidak tersedia saat pengujian, sehingga service memakai baseline deterministik | **Diterapkan dengan transparansi** — mode dilaporkan jujur via field `model_source` (`baseline`/`xgboost`), bukan diklaim sebagai keluaran model |
| ASUMSI-03 | Masa berlaku access token 30 menit dan refresh token 7 hari | **Diterapkan** — sesuai Prompt D.2; dikonfigurasi lewat `.env` |
| ASUMSI-04 | `visit_day` dibatasi tujuh hari (Monday–Sunday) dan bersifat case-insensitive | **Diterapkan** — normalisasi `capitalize()` + whitelist, selaras dengan input tunggal pada PTM-05 |
| ASUMSI-05 | `visitor_history_id` bersifat opsional pada `POST /api/predict` | **Diterapkan** — bila kosong, sistem menyiapkan histori rujukan otomatis; kontrak PTM-05 hanya mewajibkan `visit_day` |
| ASUMSI-06 | Tabel `users` ditambahkan pada ERD PTM-05 | **Diterapkan** — prasyarat mutlak autentikasi JWT; didokumentasikan sebagai penyimpangan sadar |
| ASUMSI-07 | Kolom `user_id` ditambahkan pada entitas PTM-05 | **Diterapkan** — prasyarat verifikasi kepemilikan objek (anti-BOLA) |
| ASUMSI-08 | Batas ukuran berkas 5 MB dan MIME whitelist `image/jpeg`, `image/png` | **Diterapkan** — sesuai checklist D.3; dikonfigurasi lewat `MAX_FILE_SIZE_MB` |
| ASUMSI-09 | Objek milik pengguna lain dikembalikan **403**, bukan 404 | **Diterapkan** — mengikuti aturan eksplisit pada Prompt D.3 |
| ASUMSI-10 | Endpoint unggahan berkas (`POST /api/ai/infer`) ditambahkan di luar kontrak PTM-05 | **Diterapkan** — diperlukan agar kontrol sanitasi berkas dapat diuji secara nyata; ditandai sebagai endpoint tambahan |
| ASUMSI-11 | Refresh token belum dirotasi/di-revoke | **Ditolak untuk saat ini** — di luar cakupan PTM-06, dicatat sebagai batasan pada laporan audit |
| ASUMSI-12 | Rate limiting per klien belum diterapkan | **Ditolak untuk saat ini** — batas sumber daya bersifat struktural; disarankan untuk tahap produksi |
| ASUMSI-13 | Password minimal 8 karakter dengan huruf dan angka | **Diterapkan** — kebijakan yang wajar; tidak ada spesifikasi NFR pada PTM-03/05 |
| ASUMSI-14 | Format galat seragam `{"status": "error", "message": ...}` | **Diterapkan** — memudahkan klien; diverifikasi pada seluruh kode status |

---

## 6. Log Prompt Wajib (`ptm-06-prompt-log`)

| No | Target Prompt | Alat AI & Versi | Ringkasan Prompt | Kualitas Output (1-5) | Revisi Manual |
|----|---------------|-----------------|------------------|-----------------------|---------------|
| 1 | D.1 Scaffold Modular | Asisten AI (model LLM, sesi praktikum) | Generate struktur Router-Service-Repository FastAPI dari `openapi.yaml` PTM-05, termasuk session generator DB dan `.env.example` | 4 | Struktur `models/` disatukan; resource contoh diganti domain nyata; pengecekan kepemilikan dipindah ke service |
| 2 | D.2 Autentikasi JWT | Asisten AI (model LLM, sesi praktikum) | Implementasi bcrypt, token pair (30 menit / 7 hari), dependency protected route, handler signup/login/refresh/me | 3 | Klaim `type` ditambahkan; pesan galat login disamakan; `passlib` diganti bcrypt langsung (galat 72 byte); password lemah ditolak; `UserPublic` tanpa hash |
| 3 | D.3 Audit OWASP & BOLA | Asisten AI (model LLM, sesi praktikum) | Audit 14 titik terhadap OWASP API Top 10 2023, patch anti-BOLA, helper sanitasi masukan AI | 4 | Cakupan BOLA diperluas ke PUT/DELETE/referensi lintas-resource; 404→403 pada objek milik orang lain; magic bytes ditambahkan; mass assignment diidentifikasi manual |
| 4 | Iterasi lanjutan | Asisten AI (model LLM, sesi praktikum) | Perbaiki galat bcrypt 72 byte dan seragamkan format respons galat | 5 | Dua patch presisi; diverifikasi ulang melalui seluruh 59 pengujian |

**Catatan kualitas:** skor 3 pada D.2 mencerminkan bahwa output pertama memiliki
tiga masalah nyata (pemisahan tipe token, kebocoran enumerasi akun, dan
inkompatibilitas library) yang baru terdeteksi melalui pengujian, bukan dari
pembacaan kode.

---

## 7. Hasil Verifikasi Sebagai Bukti

Hasil AI **tidak diterima berdasarkan klaim**, melainkan diverifikasi melalui
pengujian yang dapat dijalankan ulang:

| Lapis verifikasi | Perintah | Hasil |
|------------------|----------|-------|
| Pengujian otomatis | `pytest` | **59 lulus, 0 gagal** |
| Verifikasi end-to-end (server hidup) | `python verify_e2e.py` | **54 lulus, 0 gagal** |
| Cakupan celah BOLA | 8 serangan lintas pengguna | **Semuanya ditolak 403** |
| Bukti alur auth | 7 skenario (401/200/refresh) | **Semua sesuai harapan** |
| Bukti batas sumber daya | Berkas >5MB, batch >7, MIME tidak valid | **413/422/415 sesuai harapan** |

Ringkasan temuan yang ditemukan **melalui pengujian, bukan melalui AI**:

1. Inkompatibilitas `passlib` 1.7.4 dengan `bcrypt` 5.x → diperbaiki.
2. Ketidakseragaman format galat antar-endpoint → diperbaiki.
3. Referensi `visitor_history_id` lintas pengguna (BOLA lintas-resource) →
   ditemukan saat merancang skenario penyerangan dan diperbaiki.
4. Mass assignment `user_id` → ditemukan saat menguji spoofing dan diperbaiki.

---

## 8. Deklarasi Etika Penggunaan AI

Kami menyatakan bahwa:

1. AI digunakan sebagai **alat bantu draf**, bukan sebagai pengganti
   pemahaman tim terhadap arsitektur dan keamanan sistem.
2. Seluruh keluaran AI telah **diperiksa, diuji, dan direvisi** secara manual.
   Daftar revisi tercatat pada Bagian 3 dan 4.
3. Setiap klaim keamanan diverifikasi melalui pengujian yang dapat dijalankan
   ulang (`pytest` dan `verify_e2e.py`), bukan berdasarkan pernyataan AI.
4. Bagian yang bergantung pada keputusan yang belum tersedia ditandai
   `[ASUMSI-XX]` dan diverifikasi tim pada Bagian 5.
5. Keterbatasan implementasi (rotasi refresh token, rate limiting) dinyatakan
   secara terbuka pada `docs/security/owasp-audit.md` Bagian 6.
6. Tidak ada kredensial riil, kunci rahasia, atau data pribadi yang
   di-hardcode di dalam kode maupun dokumen.

| Peran | Nama | NIM | Tanda Tangan |
|-------|------|-----|--------------|
| Anggota 1 | [NAMA-1] | [NIM-1] | |
| Anggota 2 | [NAMA-2] | [NIM-2] | |
| Anggota 3 | [NAMA-3] | [NIM-3] | |

---

## 9. Status Dokumen

**Status:** Final — seluruh hasil AI telah melalui koreksi manual dan
verifikasi berbasis pengujian.

**Dokumen keluaran terkait:**

```text
.
├── .env.example
├── backend/
│   ├── app/                 (routers, services, repositories, core)
│   ├── tests/               (59 pengujian otomatis)
│   └── verify_e2e.py        (54 pemeriksaan end-to-end)
└── docs/
    ├── postman/
    │   └── postman-collection.json
    ├── prompt-log/
    │   └── ptm-06-prompt-log.md
    └── security/
        └── owasp-audit.md
```

**Pertemuan:** 06
**Fokus:** Router-Service-Repository → JWT Auth → OWASP/BOLA → Postman → Prompt Log
