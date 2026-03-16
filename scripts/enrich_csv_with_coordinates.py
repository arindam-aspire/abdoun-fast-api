"""
Script to enrich CSV file with latitude and longitude coordinates
by geocoding the location column using Nominatim API.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    try:
        # Try to set UTF-8 encoding for Windows console
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from app.utils.logger import setup_windows_console_encoding, get_coord_logger
from app.services.geocoding import geocoding_service

# Setup Windows console encoding for emojis
setup_windows_console_encoding()

# Helper function to safely print emojis on Windows
def safe_print(text: str):
    """Print text safely, handling emoji encoding on Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: replace emojis with text equivalents
        text_safe = text.encode('ascii', 'replace').decode('ascii')
        print(text_safe)


def _check_azure_openai_config(emoji_safe) -> None:
    """Check and display Azure OpenAI configuration status."""
    try:
        from app.core.config import get_settings
        settings = get_settings()
        missing = []
        if not settings.azure_openai_key:
            missing.append("AZURE_OPENAI_KEY")
        if not settings.azure_openai_endpoint:
            missing.append("AZURE_ENDPOINT")
        if not settings.azure_openai_api_version:
            missing.append("AZURE_API_VERSION")
        if not settings.azure_openai_deployment_name:
            missing.append("AZURE_DEPLOYMENT_NAME")
        
        if missing:
            safe_print(emoji_safe(f"Azure OpenAI fallback: Disabled (missing: {', '.join(missing)})"))
        else:
            try:
                import openai
                safe_print(emoji_safe("Azure OpenAI fallback: Enabled (will be used if Nominatim fails)"))
            except ImportError:
                safe_print(emoji_safe("Azure OpenAI fallback:  Configured but 'openai' library not installed"))
                print("   Install with: pip install openai==0.28.1")
    except Exception as e:
        safe_print(emoji_safe(f"Azure OpenAI fallback: Disabled (error: {str(e)})"))


def _process_row(
    idx: int,
    row: pd.Series,
    df: pd.DataFrame,
    location_column: str,
    total_rows: int,
    skip_existing: bool,
    emoji_safe
) -> tuple[int, int, int]:
    """Process a single row for geocoding. Returns (geocoded_count, skipped_count, failed_count)."""
    location = row.get(location_column)
    
    # Skip if location is empty
    if pd.isna(location) or not str(location).strip():
        safe_print(emoji_safe(f"[{idx+1}/{total_rows}]  Empty location, skipping"))
        return 0, 0, 1
    
    # Skip if coordinates already exist
    if skip_existing:
        if pd.notna(row.get("latitude")) and pd.notna(row.get("longitude")):
            safe_print(emoji_safe(f"[{idx+1}/{total_rows}] Already has coordinates, skipping: {location}"))
            return 0, 1, 0
    
    # Geocode the location
    safe_print(emoji_safe(f"[{idx+1}/{total_rows}] Geocoding: {location}"))
    coords = geocoding_service.get_coordinates_with_fallback(str(location))
    
    if coords:
        lon, lat = coords
        df.at[idx, "longitude"] = lon
        df.at[idx, "latitude"] = lat
        safe_print(emoji_safe(f"    Found: ({lat:.6f}, {lon:.6f})"))
        return 1, 0, 0
    else:
        safe_print(emoji_safe("    Not found"))
        return 0, 0, 1


def enrich_csv_with_coordinates(
    input_csv: str,
    output_csv: str | None = None,
    location_column: str = "location",
    skip_existing: bool = True,
) -> None:
    """
    Enrich CSV file with latitude and longitude coordinates.
    
    Args:
        input_csv: Path to input CSV file
        output_csv: Path to output CSV file (if None, overwrites input)
        location_column: Name of the column containing location strings
        skip_existing: If True, skip rows that already have lat/lng
    """
    _, emoji_safe = get_coord_logger()
    safe_print(emoji_safe(f"Reading CSV: {input_csv}"))
    df = pd.read_csv(input_csv)
    
    # Check if location column exists
    if location_column not in df.columns:
        safe_print(emoji_safe(f"Error: Column '{location_column}' not found in CSV"))
        print(f"Available columns: {', '.join(df.columns)}")
        sys.exit(1)
    
    # Initialize lat/lng columns if they don't exist
    if "latitude" not in df.columns:
        df["latitude"] = None
    if "longitude" not in df.columns:
        df["longitude"] = None
    
    total_rows = len(df)
    geocoded_count = 0
    skipped_count = 0
    failed_count = 0
    
    safe_print(emoji_safe(f"Processing {total_rows} properties..."))
    safe_print(emoji_safe("Rate limited to 1 request/second (Nominatim policy)"))
    
    _check_azure_openai_config(emoji_safe)
    
    print("-" * 60)
    
    for idx, row in df.iterrows():
        geocoded, skipped, failed = _process_row(
            idx, row, df, location_column, total_rows, skip_existing, emoji_safe
        )
        geocoded_count += geocoded
        skipped_count += skipped
        failed_count += failed
    
    # Save enriched CSV
    output_path = output_csv or input_csv
    print("-" * 60)
    safe_print(emoji_safe(f"Saving enriched CSV to: {output_path}"))
    df.to_csv(output_path, index=False)
    
    # Print summary
    print("\n" + "=" * 60)
    safe_print(emoji_safe("SUMMARY"))
    print("=" * 60)
    print(f"Total properties:     {total_rows}")
    safe_print(emoji_safe(f"Geocoded:          {geocoded_count}"))
    safe_print(emoji_safe(f"Skipped (existing): {skipped_count}"))
    safe_print(emoji_safe(f"Failed:            {failed_count}"))
    print(f"Success rate:      {(geocoded_count / (total_rows - skipped_count) * 100):.1f}%" if (total_rows - skipped_count) > 0 else "N/A")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Enrich CSV file with latitude/longitude coordinates by geocoding locations"
    )
    parser.add_argument(
        "input_csv",
        help="Path to input CSV file"
    )
    parser.add_argument(
        "-o", "--output",
        help="Path to output CSV file (default: overwrites input)",
        default=None
    )
    parser.add_argument(
        "-c", "--column",
        help="Name of location column (default: 'location')",
        default="location"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Re-geocode even if coordinates already exist"
    )
    
    args = parser.parse_args()
    
    enrich_csv_with_coordinates(
        input_csv=args.input_csv,
        output_csv=args.output,
        location_column=args.column,
        skip_existing=not args.no_skip_existing,
    )


if __name__ == "__main__":
    main()

