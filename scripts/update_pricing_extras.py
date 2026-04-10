import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.property_normalized import PropertyNormalized
from app.services.normalized_importer import _normalize_string
from app.services.normalized_importer import _parse_rent_commission

CSV_PATH = "data/abdoun_merged_properties.csv"


def _rent_commission_equal(db_val, new_val: float | None) -> bool:
    if db_val is None and new_val is None:
        return True
    if db_val is None or new_val is None:
        return False
    return abs(float(db_val) - float(new_val)) < 1e-9


def _str_equal(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return str(a).strip() == str(b).strip()


def update_pricing_fields():
    db = SessionLocal()
    df = pd.read_csv(CSV_PATH)

    processed = 0
    csv_urls: list[str] = []
    for _, row in df.iterrows():
        url = _normalize_string(row.get("url"))
        if url:
            csv_urls.append(url)

    urls = list(set(csv_urls))
    rows = db.execute(
        select(
            PropertyNormalized.id,
            PropertyNormalized.url,
            PropertyNormalized.rent_commission_percent,
            PropertyNormalized.contract_duration,
            PropertyNormalized.payment_method,
        ).where(PropertyNormalized.url.in_(urls))
    ).all()
    props_by_url = {r.url: r for r in rows if r.url}

    for _, row in df.iterrows():
        url = _normalize_string(row.get("url"))
        if not url:
            continue

        prop = props_by_url.get(url)
        if not prop:
            continue

        new_rent = _parse_rent_commission(row.get("rent_commission"))

        contract_raw = _normalize_string(row.get("contract_duration"))
        if contract_raw and contract_raw.lower() not in {
            "undefined",
            "غير محدد",
            "-- مدة العقد --",
        }:
            new_contract = contract_raw
        else:
            new_contract = None

        payment_raw = _normalize_string(row.get("payment_method"))
        new_payment = payment_raw.strip().lower() if payment_raw else None

        if not (
            _rent_commission_equal(prop.rent_commission_percent, new_rent)
            and _str_equal(prop.contract_duration, new_contract)
            and _str_equal(prop.payment_method, new_payment)
        ):
            db.execute(
                update(PropertyNormalized)
                .where(PropertyNormalized.id == prop.id)
                .values(
                    rent_commission_percent=new_rent,
                    contract_duration=new_contract,
                    payment_method=new_payment,
                )
            )

        processed += 1

    db.commit()
    db.close()

    print(f"Updated {processed} properties")

if __name__ == "__main__":
    update_pricing_fields()
