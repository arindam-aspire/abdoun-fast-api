"""Unit tests for app.services.property_import_service."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.property_import_service import PropertyImportService


async def _run_import():
    mock_db = MagicMock()
    mock_file = MagicMock()
    with patch(
        "app.services.property_import_service.import_properties_from_csv_file",
        new_callable=AsyncMock,
        return_value=3,
    ) as mock_import:
        svc = PropertyImportService(mock_db)
        out = await svc.import_from_csv(mock_file, geocode_missing=True)
        assert out == 3
        mock_import.assert_called_once_with(mock_db, mock_file, geocode_missing=True)


def test_import_from_csv_calls_importer():
    asyncio.run(_run_import())
