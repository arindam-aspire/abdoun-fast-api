import pandas as pd
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.property_normalized import PropertyNormalized
from app.services.normalized_importer import _parse_rent_commission
from app.services.normalized_importer import _normalize_string

CSV_PATH = "data/abdoun_merged_properties.csv"

def update_pricing_fields():
    db = SessionLocal()
    df = pd.read_csv(CSV_PATH)

    updated = 0

    for _, row in df.iterrows():
        url = _normalize_string(row.get("url"))
        if not url:
            continue

        prop = db.execute(
            select(PropertyNormalized).where(PropertyNormalized.url == url)
        ).scalar_one_or_none()

        if not prop:
            continue

        # --- rent commission ---
        prop.rent_commission_percent = _parse_rent_commission(
            row.get("rent_commission")
        )

        # --- contract duration ---
        contract_raw = _normalize_string(row.get("contract_duration"))
        if contract_raw and contract_raw.lower() not in {"undefined", "غير محدد", "-- مدة العقد --"}:
            prop.contract_duration = contract_raw
        else:
            prop.contract_duration = None

        # --- payment method ---
        payment_raw = _normalize_string(row.get("payment_method"))
        prop.payment_method = payment_raw.strip().lower() if payment_raw else None

        updated += 1

    db.commit()
    db.close()

    print(f"Updated {updated} properties")

if __name__ == "__main__":
    update_pricing_fields()
