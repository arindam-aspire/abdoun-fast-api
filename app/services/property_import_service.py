"""Property CSV import service; wraps csv_importer, router delegates here (no direct DB in router)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.csv_importer import import_properties_from_csv_file


class PropertyImportService:
    """Service for property CSV import. Uses session for DB access via importer."""

    def __init__(self, db: Session) -> None:
        """Store the database session for import.

        Args:
            db: SQLAlchemy Session (request-scoped).
        """
        self._db = db

    async def import_from_csv(
        self,
        file,
        *,
        geocode_missing: bool = False,
    ) -> int:
        """Import properties from CSV file. Returns count of created records."""
        return await import_properties_from_csv_file(
            self._db, file, geocode_missing=geocode_missing
        )
