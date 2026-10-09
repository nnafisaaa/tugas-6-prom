"""Bootstrap aplikasi: membuat tabel dan seed data demonstran.

Jalankan sekali setelah ``pip install -r requirements.txt``:

    python init_db.py

Skrip ini idempoten: aman dijalankan berulang.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import PredictionResult, User, VisitorHistory

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "Demo12345"


def main() -> None:
    """Buat skema tabel dan satu akun demonstrasi beserta datanya."""
    print(f"Menyiapkan basis data: {settings.DATABASE_URL}")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if existing is not None:
            print(f"Akun demo sudah ada: {DEMO_EMAIL}")
            return

        user = User(
            name="Akun Demo",
            email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        history = VisitorHistory(
            user_id=user.id,
            visit_date="2025-06-01",
            visit_day="Sunday",
            visitor_total=3200,
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        db.add(
            PredictionResult(
                user_id=user.id,
                visitor_history_id=history.id,
                visit_day="Sunday",
                prediction_value=3100,
            )
        )
        db.commit()

        print("Basis data siap.")
        print(f"  Akun demo : {DEMO_EMAIL}")
        print(f"  Password  : {DEMO_PASSWORD}")
        print("  Sekret    : disimpan sebagai hash bcrypt, bukan plaintext")
    finally:
        db.close()


if __name__ == "__main__":
    main()
