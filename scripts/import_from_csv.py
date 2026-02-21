import argparse
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.services.csv_importer import import_properties_from_dataframe


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import properties from CSV into the database."
    )
    parser.add_argument("csv_path", help="Path to the CSV file")
    parser.add_argument(
        "--geocode-missing",
        action="store_true",
        help="Geocode locations that don't have coordinates (slower, rate-limited)"
    )
    parser.add_argument(
        "--update-coordinates",
        action="store_true",
        help="Update coordinates for existing properties that have missing coordinates"
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    df = pd.read_csv(args.csv_path)

    with SessionLocal() as session:
        result = import_properties_from_dataframe(
            session, 
            df, 
            geocode_missing=args.geocode_missing,
            update_coordinates=args.update_coordinates
        )
        print(f"Total processed: {result} properties.")


if __name__ == "__main__":
    main()








