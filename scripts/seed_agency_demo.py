"""Seed a demo agency through the service layer for local testing."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.repositories.agency_repository import AgencyRepository
from app.schemas.agency import AgencyRegisterRequest
from app.services.agency_service import AgencyService


def seed_agency_demo() -> None:
    with SessionLocal() as db:
        service = AgencyService(AgencyRepository(db))
        service.register(
            AgencyRegisterRequest(
                email="demo-agency@example.com",
                phone_number="+962790000001",
                agency_name="Demo Agency LLC",
                agency_trade_name="Demo Agency",
                password="AgencyPass1!",
                file_name="legal_document.pdf",
                content_type="application/pdf",
                address="1 Demo Street",
                city="Amman",
                country="Jordan",
                website="https://example.com",
            )
        )
        print("Seeded demo agency: demo-agency@example.com / AgencyPass1!")


if __name__ == "__main__":
    seed_agency_demo()
