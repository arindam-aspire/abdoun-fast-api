"""Import legacy Abdoun Excel exports into property_listing_submissions.

Usage:
  # Dry run (recommended first)
  python scripts/import_legacy_excel_properties.py --dry-run

  # Import all rows
  python scripts/import_legacy_excel_properties.py --submitter-email admin@example.com

  # Test with first 10 rows
  python scripts/import_legacy_excel_properties.py --dry-run --limit 10

  # Regenerate Excel from source files, then import
  python scripts/import_legacy_excel_properties.py --transform-first --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.db.session import SessionLocal
from app.models.live_schema import AgencyMaster, User
from app.services.legacy_excel_importer import import_legacy_excel

DEFAULT_EXCEL = Path(r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Import_Ready.xlsx")
DEFAULT_OWNERS = Path(r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Property_Owners.xlsx")
DEFAULT_RECORDS = Path(r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Property_Records.xlsx")


def _resolve_agency(db, agency_id: str | None) -> AgencyMaster:
    if agency_id:
        agency = db.get(AgencyMaster, UUID(agency_id))
        if agency is None:
            raise RuntimeError(f"Agency not found: {agency_id}")
        return agency

    agency = db.execute(
        select(AgencyMaster)
        .where(AgencyMaster.status == "ACTIVE")
        .order_by(AgencyMaster.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if agency is None:
        agency = db.execute(select(AgencyMaster).order_by(AgencyMaster.created_at.asc()).limit(1)).scalar_one_or_none()
    if agency is None:
        raise RuntimeError("No agency found. Pass --agency-id explicitly.")
    return agency


def _resolve_submitter(db, email: str | None) -> User:
    if email:
        submitter = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if submitter is None:
            raise RuntimeError(f"Submitter user not found: {email}")
        return submitter

    submitter = db.execute(select(User).order_by(User.created_at.asc())).scalars().first()
    if submitter is None:
        raise RuntimeError("No users found in database. Pass --submitter-email explicitly.")
    return submitter


def _load_workbook(excel_path: Path) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    properties_df = pd.read_excel(excel_path, sheet_name="property_listing_submissions")
    try:
        owners_df = pd.read_excel(excel_path, sheet_name="users_owners")
    except ValueError:
        owners_df = None
    try:
        media_df = pd.read_excel(excel_path, sheet_name="property_media")
    except ValueError:
        media_df = None
    return properties_df, owners_df, media_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy Abdoun Excel data into the current database.")
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL), help="Path to Abdoun_Import_Ready.xlsx")
    parser.add_argument("--transform-first", action="store_true", help="Regenerate import workbook from source Excel files")
    parser.add_argument("--source-owners", default=str(DEFAULT_OWNERS))
    parser.add_argument("--source-records", default=str(DEFAULT_RECORDS))
    parser.add_argument("--submitter-email", default=None, help="Fallback submitter when property has no owner user")
    parser.add_argument("--agency-id", default=None, help="Agency UUID (defaults to first ACTIVE agency)")
    parser.add_argument("--media-base-url", default=None, help="Prefix URL for photo filenames, e.g. https://cdn.example.com/legacy")
    parser.add_argument("--dry-run", action="store_true", help="Plan import without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Import only first N properties")
    parser.add_argument("--skip-owners", action="store_true", help="Do not create/link owner users")
    args = parser.parse_args()

    excel_path = Path(args.excel)
    if args.transform_first:
        from transform_legacy_excel_for_import import transform

        transform(Path(args.source_owners), Path(args.source_records), excel_path)
        print({"transformed_to": str(excel_path)})

    properties_df, owners_df, media_df = _load_workbook(excel_path)

    db = SessionLocal()
    try:
        submitter = _resolve_submitter(db, args.submitter_email)
        agency = _resolve_agency(db, args.agency_id)
        result = import_legacy_excel(
            db,
            properties_df=properties_df,
            owners_df=owners_df,
            submitter=submitter,
            agency_id=agency.id,
            dry_run=args.dry_run,
            limit=args.limit,
            skip_owners=args.skip_owners,
            media_df=media_df,
            media_base_url=args.media_base_url,
        )
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
