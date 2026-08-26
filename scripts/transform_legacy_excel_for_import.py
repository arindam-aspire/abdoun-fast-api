"""Transform legacy Abdoun Property Excel exports into DB-aligned import workbooks.

Source files (defaults):
  - Abdoun_Property_Owners.xlsx
  - Abdoun_Property_Records.xlsx

Output workbook sheets:
  1. property_listing_submissions
  2. users_owners
  3. property_media
  4. column_mapping
  5. taxonomy_reference
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from uuid import UUID, uuid5

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SOURCE_NAMESPACE = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

PROPERTY_TYPE_MAP = {
    "شقة": ("residential", "apartments", "Apartments"),
    "فيلا": ("residential", "villas", "Villas"),
    "أرض": ("land", "residential-lands", "Residential Lands"),
    "مكتب": ("commercial", "offices", "Offices"),
    "مجمع تجاري": ("commercial", "businesses", "Businesses"),
    "مزرعة": ("residential", "farms", "Farms"),
    "فرصة استثمارية": ("commercial", "businesses", "Businesses"),
}

OFFER_TYPE_MAP = {
    "For Sale": "sale",
    "For Rent": "rent",
    "For Sale or Rent": "sale_or_rent",
    "Not Specified": "unspecified",
}

LISTING_STATUS_MAP = {
    "Available": "active",
    "Sold": "deal-closed",
    "Rented": "deal-closed",
}

CITY_MAP = {
    "عمان": "Amman",
    "السلط": "Salt",
    "ناعور": "Naour",
    "العقبة": "Aqaba",
    "مأدبا": "Madaba",
    "جرش": "Jerash",
    "المفرق": "Mafraq",
    "صويلح": "Sweileh",
    "الطفيلة": "Tafilah",
    "معان": "Ma'an",
}


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "no linked owner"}:
        return None
    return text


def _price(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[\d.]+", text)
    return match.group(0) if match else None


def _int(value) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _owner_key(name: str | None, phone: str | None, email: str | None) -> str | None:
    if email:
        return f"email:{email.lower()}"
    if phone:
        digits = re.sub(r"\D", "", phone)
        if digits:
            return f"phone:{digits}"
    if name:
        return f"name:{name.lower()}"
    return None


def _deterministic_property_id(export_ref: str) -> str:
    return str(uuid5(SOURCE_NAMESPACE, export_ref))


def _deterministic_owner_id(owner_key: str) -> str:
    return str(uuid5(SOURCE_NAMESPACE, f"owner:{owner_key}"))


def _infer_listing_purpose(offer_type: str | None, sale_price, rent_price) -> str:
    mapped = OFFER_TYPE_MAP.get(offer_type or "", "unspecified")
    if mapped == "sale":
        return "sale"
    if mapped == "rent":
        return "rent"
    if mapped == "sale_or_rent":
        if _price(sale_price) and not _price(rent_price):
            return "sale"
        if _price(rent_price) and not _price(sale_price):
            return "rent"
        return "sale_or_rent"
    if _price(sale_price) and not _price(rent_price):
        return "sale"
    if _price(rent_price) and not _price(sale_price):
        return "rent"
    return "sale"


def transform(owners_path: Path, records_path: Path, output_path: Path) -> dict[str, int]:
    owners = pd.read_excel(owners_path)
    records = pd.read_excel(records_path)

    merged = records.merge(
        owners,
        left_on="Export Reference",
        right_on="Property Export Reference",
        how="left",
        suffixes=("", "_owner"),
    )

    property_rows: list[dict] = []
    owner_rows: dict[str, dict] = {}
    media_rows: list[dict] = []

    for _, row in merged.iterrows():
        export_ref = _clean(row.get("Export Reference"))
        if not export_ref:
            continue

        property_type_raw = _clean(row.get("Property Type"))
        category_slug, type_slug, type_name = PROPERTY_TYPE_MAP.get(
            property_type_raw or "",
            ("residential", "apartments", "Apartments"),
        )

        offer_type = _clean(row.get("Offer Type"))
        listing_purpose = _infer_listing_purpose(
            offer_type,
            row.get("Sale Price"),
            row.get("Rent Price"),
        )

        listing_status = _clean(row.get("Listing Status")) or "Available"
        submission_status = LISTING_STATUS_MAP.get(listing_status, "active")

        city_ar = _clean(row.get("Governorate / City"))
        city_en = CITY_MAP.get(city_ar or "", city_ar)
        area_name = _clean(row.get("Area / Neighbourhood"))

        owner_name = _clean(row.get("Owner Name or Company Name"))
        owner_phone = _clean(row.get("Primary Mobile Number"))
        owner_phone2 = _clean(row.get("Secondary Mobile Number"))
        owner_email = _clean(row.get("Email Address"))
        owner_key = _owner_key(owner_name, owner_phone, owner_email)

        property_id = _deterministic_property_id(export_ref)
        owner_user_id = _deterministic_owner_id(owner_key) if owner_key else None

        default_country = os.getenv("DEFAULT_COUNTRY") or ""
        title = _clean(row.get("Property Title")) or f"{type_name} in {area_name or city_en or default_country}".strip()
        sale_price = _price(row.get("Sale Price"))
        rent_price = _price(row.get("Rent Price"))
        price = sale_price if listing_purpose in {"sale", "sale_or_rent"} else rent_price
        if not price:
            price = sale_price or rent_price

        import_notes: list[str] = []
        if property_type_raw and property_type_raw not in PROPERTY_TYPE_MAP:
            import_notes.append(f"Unknown property type: {property_type_raw}")
        if listing_purpose == "sale_or_rent":
            import_notes.append("Both sale and rent prices present; review listing_purpose manually")
        if offer_type == "Not Specified":
            import_notes.append("Offer type was Not Specified; inferred from prices")
        if not owner_key:
            import_notes.append("No owner contact info; owner_information will use placeholder")
        if submission_status == "deal-closed":
            import_notes.append(f"Legacy status was {listing_status}; mapped to deal-closed")

        property_rows.append(
            {
                "export_reference": export_ref,
                "property_id": property_id,
                "submitted_by_user_id": "",
                "agency_id": "",
                "status": submission_status,
                "current_step": 8,
                "last_completed_step": 8,
                "listing_purpose": listing_purpose,
                "category_slug": category_slug,
                "type_slug": type_slug,
                "category_id": "",
                "type_id": "",
                "title": title,
                "description": _clean(row.get("Public Description")),
                "city_name_en": city_en,
                "city_id": "",
                "area_name": area_name,
                "area_id": "",
                "address": _clean(row.get("Location / Address")),
                "latitude": row.get("Latitude") if pd.notna(row.get("Latitude")) else None,
                "longitude": row.get("Longitude") if pd.notna(row.get("Longitude")) else None,
                "price": price,
                "sale_price": sale_price,
                "rent_price": rent_price,
                "currency": (os.getenv("DEFAULT_CURRENCY") or "").upper() or None,
                "bedrooms": _int(row.get("Bedrooms")),
                "bathrooms": _int(row.get("Bathrooms")),
                "built_up_area_sqm": _int(row.get("Building Area (sq m)")),
                "land_area_sqm": _int(row.get("Land Area (sq m)")),
                "floor_number": _int(row.get("Floor Number")),
                "total_floors": _int(row.get("Total Floors")),
                "construction_year": _int(row.get("Construction Year")),
                "furnishing": _clean(row.get("Furnishing")),
                "finishing": _clean(row.get("Finishing")),
                "parking": _clean(row.get("Parking")),
                "heating": _clean(row.get("Heating")),
                "view": _clean(row.get("View")),
                "features_amenities": _clean(row.get("Features & Amenities")),
                "listing_date": row.get("Listing Date"),
                "owner_user_id": owner_user_id or "",
                "owner_full_name": owner_name or "Legacy Property Owner",
                "owner_email": owner_email or "",
                "owner_phone": owner_phone or "",
                "owner_secondary_phone": owner_phone2 or "",
                "legacy_offer_type": offer_type,
                "legacy_listing_status": listing_status,
                "legacy_property_type_ar": property_type_raw,
                "photo_count": _int(row.get("Number of Photographs")) or 0,
                "photo_filenames": _clean(row.get("Exported Photograph Filenames")),
                "import_notes": "; ".join(import_notes),
            }
        )

        if owner_key and owner_key not in owner_rows:
            owner_rows[owner_key] = {
                "owner_key": owner_key,
                "owner_user_id": owner_user_id,
                "full_name": owner_name or "Legacy Property Owner",
                "email": owner_email or f"legacy-owner-{owner_user_id[:8]}@import.local",
                "phone_number": owner_phone or "",
                "secondary_phone": owner_phone2 or "",
                "preferred_language": "ar",
                "role_name": "owner",
                "agency_id": "",
                "is_active": True,
                "import_notes": "Create user + user_roles(owner) + user_agency_mappings(property_owner) before import",
            }

        photo_filenames = _clean(row.get("Exported Photograph Filenames"))
        if photo_filenames:
            for index, filename in enumerate(part.strip() for part in photo_filenames.split(",") if part.strip()):
                media_rows.append(
                    {
                        "export_reference": export_ref,
                        "property_id": property_id,
                        "media_type": "image",
                        "url": "",
                        "file_name": filename,
                        "display_order": index,
                        "is_primary": index == 0,
                        "import_notes": "Upload file to S3/media storage and fill url before DB insert",
                    }
                )

    for owner_key in owner_rows:
        owner_rows[owner_key]["linked_properties_count"] = sum(
            1 for row in property_rows if row.get("owner_user_id") == owner_rows[owner_key]["owner_user_id"]
        )

    mapping_rows = [
        {"legacy_column": "Export Reference", "target_table": "property_listing_submissions", "target_column": "export_reference / payload._seed.source_id", "notes": "Unique legacy key; keep for deduplication"},
        {"legacy_column": "Property Title", "target_table": "property_listing_submissions.payload", "target_column": "basic_information.title", "notes": "Required display title"},
        {"legacy_column": "Offer Type", "target_table": "property_listing_submissions.payload", "target_column": "basic_information.listing_purpose", "notes": "For Sale→sale, For Rent→rent"},
        {"legacy_column": "Listing Status", "target_table": "property_listing_submissions", "target_column": "status", "notes": "Available→active, Sold/Rented→deal-closed"},
        {"legacy_column": "Property Type (Arabic)", "target_table": "property_listing_submissions.payload", "target_column": "basic_information.category_id + type_id", "notes": "Resolve slugs to IDs from taxonomy_reference sheet"},
        {"legacy_column": "Governorate / City", "target_table": "property_listing_submissions.payload", "target_column": "location.city_id", "notes": "Match city name against cities table"},
        {"legacy_column": "Area / Neighbourhood", "target_table": "property_listing_submissions.payload", "target_column": "location.area_id", "notes": "Match area under selected city"},
        {"legacy_column": "Location / Address", "target_table": "property_listing_submissions.payload", "target_column": "location.address", "notes": ""},
        {"legacy_column": "Latitude / Longitude", "target_table": "property_listing_submissions.payload", "target_column": "location.latitude / location.longitude", "notes": ""},
        {"legacy_column": "Sale Price / Rent Price", "target_table": "property_listing_submissions.payload", "target_column": "pricing.price + pricing.currency", "notes": "Use sale price for sale listings, rent price for rent listings"},
        {"legacy_column": "Bedrooms / Bathrooms / Areas", "target_table": "property_listing_submissions.payload", "target_column": "property_details.*", "notes": ""},
        {"legacy_column": "Owner Name / Phone / Email", "target_table": "users + payload.owner_information", "target_column": "users.full_name/email/phone + owner_information.owners[]", "notes": "Owners are users in current system, not owner table"},
        {"legacy_column": "Exported Photograph Filenames", "target_table": "property_media", "target_column": "url, file_name, display_order", "notes": "Upload images first, then insert rows"},
    ]

    taxonomy_rows = [
        {"legacy_property_type_ar": k, "category_slug": v[0], "type_slug": v[1], "type_name_en": v[2]}
        for k, v in PROPERTY_TYPE_MAP.items()
    ]

    submissions_df = pd.DataFrame(property_rows)
    owners_df = pd.DataFrame(list(owner_rows.values()))
    media_df = pd.DataFrame(media_rows)
    mapping_df = pd.DataFrame(mapping_rows)
    taxonomy_df = pd.DataFrame(taxonomy_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        submissions_df.to_excel(writer, sheet_name="property_listing_submissions", index=False)
        owners_df.to_excel(writer, sheet_name="users_owners", index=False)
        media_df.to_excel(writer, sheet_name="property_media", index=False)
        mapping_df.to_excel(writer, sheet_name="column_mapping", index=False)
        taxonomy_df.to_excel(writer, sheet_name="taxonomy_reference", index=False)

    return {
        "properties": len(submissions_df),
        "owners": len(owners_df),
        "media_rows": len(media_df),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform legacy Abdoun Excel exports for current DB import.")
    parser.add_argument(
        "--owners",
        default=r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Property_Owners.xlsx",
    )
    parser.add_argument(
        "--records",
        default=r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Property_Records.xlsx",
    )
    parser.add_argument(
        "--output",
        default=r"c:\Users\Sukanya Hazra\Downloads\Abdoun_Import_Ready.xlsx",
    )
    args = parser.parse_args()

    summary = transform(Path(args.owners), Path(args.records), Path(args.output))
    print(summary)


if __name__ == "__main__":
    main()
