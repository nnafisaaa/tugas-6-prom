"""Utilitas keamanan: hashing password bcrypt dan JWT token pair.

Prinsip:
- Password TIDAK PERNAH disimpan atau di-log dalam bentuk plaintext.
- Kunci penandatanganan diambil dari environment (``SECRET_KEY``).
- Claims JWT hanya memuat identitas non-rahasia (``sub``, ``type``, ``exp``, ``iat``).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt

from app.core.config import settings

# ------------------------------------------------------------------------------
# Password hashing (bcrypt)
# ------------------------------------------------------------------------------

# bcrypt memotong input pada 72 byte; batasi agar konsisten dan aman.
BCRYPT_MAX_BYTES = 72


def _bcrypt_secret(password: str) -> bytes:
    """Ubah password menjadi byte untuk bcrypt, dipotong tepat pada 72 byte.

    Pemotongan dilakukan sendiri (bukan diserahkan ke library) karena versi
    ``bcrypt`` terbaru melempar ValueError bila input melebihi 72 byte, dan
    versi ``passlib`` tertentu tidak lagi menanganinya secara otomatis.
    """
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash password dengan bcrypt (salt dibangkitkan otomatis)."""
    import bcrypt

    return bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifikasi password terhadap hash bcrypt secara aman."""
    import bcrypt

    try:
        return bcrypt.checkpw(_bcrypt_secret(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Hash tidak valid / korup -> anggap gagal verifikasi.
        return False


# ------------------------------------------------------------------------------
# JWT token pair
# ------------------------------------------------------------------------------

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Dibangkitkan saat token tidak valid atau kedaluwarsa."""


def _create_token(subject: str, token_type: TokenType, expires_delta: timedelta) -> str:
    """Buat token JWT bertanda tangan dengan claims minimal."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    # DILARANG menaruh password hash / secret apa pun di dalam claims.
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | int) -> str:
    """Terbitkan access token berdurasi pendek (default 30 menit)."""
    return _create_token(
        str(subject),
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: str | int) -> str:
    """Terbitkan refresh token berdurasi panjang (default 7 hari)."""
    return _create_token(
        str(subject),
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_token_pair(subject: str | int) -> dict[str, Any]:
    """Terbitkan pasangan access token + refresh token."""
    return {
        "access_token": create_access_token(subject),
        "refresh_token": create_refresh_token(subject),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """Dekode dan validasi token.

    Raises:
        TokenError: bila signature/expiry tidak valid atau ``type`` tidak cocok.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:  # signature salah, kedaluwarsa, malformed
        raise TokenError("Token tidak valid atau telah kedaluwarsa") from exc

    if payload.get("type") != expected_type:
        raise TokenError(f"Jenis token tidak sesuai, diharapkan '{expected_type}'")

    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token tidak memuat subject")

    return payload


# ------------------------------------------------------------------------------
# Sanitasi masukan fitur AI (OWASP API1/API4 - Prompt Injection & Upload)
# ------------------------------------------------------------------------------

#: Pola indikasi prompt injection / jailbreak yang lazim.
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"(system|developer)\s*:\s*",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"abaikan\s+(semua\s+)?(instruksi|perintah)\s+(sebelumnya|di atas)",
    r"lupakan\s+(semua\s+)?(instruksi|perintah)",
    r"</?\s*(script|iframe|img|svg)\b",
    r"\{\{.*?\}\}",  # template injection
    r"\$\{.*?\}",  # ekspresi shell/JS
    r"\x00",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE | re.DOTALL)


def sanitize_ai_text(value: str, *, max_length: int | None = None) -> str:
    """Bersihkan teks masukan fitur AI dari karakter kontrol dan pola injeksi.

    Args:
        value: Teks masukan mentah.
        max_length: Batas panjang akhir (default dari settings).

    Returns:
        Teks yang telah dinormalisasi dan dibersihkan.
    """
    limit = max_length or settings.MAX_TEXT_LENGTH

    # 1) Normalisasi unicode (ubah kompatibilitas karakter penuh -> ASCII).
    cleaned = unicodedata.normalize("NFKC", value)

    # 2) Buang karakter kontrol kecuali tab/baris baru (yang lalu jadi spasi).
    cleaned = "".join(
        " " if ch in "\t\r\n" else ch
        for ch in cleaned
        if ch == "\t" or ch == "\n" or ch == "\r" or unicodedata.category(ch)[0] != "C"
    )

    # 3) Netralkan frasa prompt injection dengan menandainya.
    cleaned = _INJECTION_RE.sub("[FILTERED]", cleaned)

    # 4) Rapikan spasi berlebih dan potong panjangnya.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


#: Whitelist MIME type untuk unggahan berkas fitur AI.
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

#: Tipe berkas yang selalu ditolak, apa pun klaim MIME-nya.
BLOCKED_EXTENSIONS = {
    ".php", ".phtml", ".phar", ".jsp", ".asp", ".aspx", ".cgi",
    ".exe", ".dll", ".so", ".sh", ".bat", ".cmd", ".ps1", ".py", ".rb",
    ".js", ".mjs", ".html", ".htm", ".svg", ".xml", ".jar", ".war",
}


def validate_upload(content_type: str | None, filename: str | None, size_bytes: int) -> tuple[str, str]:
    """Validasi metadata unggahan berkas fitur AI.

    Args:
        content_type: Nilai header Content-Type dari multipart.
        filename: Nama berkas asli dari klien.
        size_bytes: Ukuran berkas dalam byte.

    Returns:
        Tuple ``(mime_type, safe_extension)``.

    Raises:
        ValueError: Bila ukuran melebihi batas, MIME tidak di-whitelist,
            atau ekstensi masuk daftar blokir.
    """
    if size_bytes <= 0:
        raise ValueError("Berkas kosong tidak diizinkan")
    if size_bytes > settings.max_file_size_bytes:
        raise ValueError(
            f"Ukuran berkas melebihi batas {settings.MAX_FILE_SIZE_MB} MB"
        )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
        raise ValueError(f"Tipe MIME tidak diizinkan. Hanya: {allowed}")

    safe_name = (filename or "").strip().lower()
    extension = ""
    if "." in safe_name:
        extension = "." + safe_name.rsplit(".", 1)[-1]
    if extension in BLOCKED_EXTENSIONS:
        raise ValueError("Ekstensi berkas tidak diizinkan")

    return mime, ALLOWED_MIME_TYPES[mime]


#: Magic bytes minimum untuk memastikan isi berkas benar-benar gambar.
_MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def verify_file_signature(content: bytes, mime_type: str) -> None:
    """Pastikan isi berkas sesuai magic bytes tipe yang diklaim.

    Raises:
        ValueError: Bila signature tidak cocok (indikasi MIME spoofing).
    """
    signatures = _MAGIC_SIGNATURES.get(mime_type, ())
    if not signatures:
        raise ValueError("Tipe berkas tidak didukung untuk verifikasi isi")
    if not any(content.startswith(sig) for sig in signatures):
        raise ValueError("Isi berkas tidak sesuai dengan tipe MIME yang diklaim")
