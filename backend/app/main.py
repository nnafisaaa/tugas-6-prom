"""Entrypoint aplikasi FastAPI — PTM-06 IMWAD.

Arsitektur modular tiga lapisan:
    Router (HTTP)  ->  Service (bisnis/otorisasi)  ->  Repository (query DB)

Jalankan dengan::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import Base, engine
from app.models import HealthResponse  # noqa: F401  (memastikan model ter-import)
from app.routers import ai_inference, auth, history, predictions

logger = logging.getLogger("imwad.ptm06")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Siapkan basis data saat aplikasi start."""
    Base.metadata.create_all(bind=engine)
    if settings.is_default_secret:
        logger.warning(
            "SECRET_KEY masih bernilai default. Ganti sebelum penggunaan nyata."
        )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ------------------------------------------------------------------------------
# Exception handlers — format galat konsisten, tanpa membocorkan detail internal
# ------------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Ubah ``HTTPException`` menjadi format ``{status, message}`` yang seragam.

    Tanpa handler ini, FastAPI mengembalikan ``{"detail": ...}`` sehingga format
    galat berbeda antar-endpoint dan menyulitkan klien.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
        headers=dict(getattr(exc, "headers", None) or {}),
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Ubah galat validasi Pydantic menjadi 422 dengan format terstandar."""
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = first.get("msg", "Data masukan tidak valid")
    detail = f"{location}: {message}" if location else message
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "message": detail},
    )


@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    """Tangani pelanggaran constraint DB sebagai 409, bukan 500."""
    logger.warning("IntegrityError: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"status": "error", "message": "Data bertentangan dengan constraint"},
    )


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    """Fallback terakhir: log detail, kembalikan pesan generik ke klien."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "Terjadi kesalahan pada server"},
    )


# ------------------------------------------------------------------------------
# Routers
# ------------------------------------------------------------------------------

app.include_router(auth.router)
app.include_router(history.router)
app.include_router(predictions.router)
app.include_router(ai_inference.router)


@app.get("/", tags=["System"], summary="Root info")
def root() -> dict:
    """Informasi singkat API."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["System"], summary="Health check")
def health() -> HealthResponse:
    """Status aplikasi dan apakah model AI berhasil dimuat."""
    from app.services.prediction_service import _model_loader

    info = _model_loader.info()
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        model_loaded=info.loaded,
    )
