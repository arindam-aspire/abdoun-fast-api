"""
Backfill property_translations from existing properties_normalized.

1) English: for each property with no 'en' row, insert (property_id, 'en', title, description).
2) Other languages: with --translate-other-languages, create ar, esp, fr rows by
   translating from en (uses deep_translator/Google when available). Uses parallel
   workers to speed up.

Run after applying migration 0007_add_property_translations.
Usage:
  python scripts/backfill_property_translations.py
  python scripts/backfill_property_translations.py --translate-other-languages
  python scripts/backfill_property_translations.py --status   # show DB counts only
"""
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, exists, func

from app.db.session import SessionLocal
from app.models.property_normalized import PropertyNormalized, PropertyTranslation
from app.services.translation_service import (
    get_or_create_translation,
    translate_property_to_language,
    translate_text,
)


def backfill_en_translations(dry_run: bool = False) -> int:
    """
    Insert property_translations (en) from properties_normalized.title/description
    where no en translation exists yet.

    Returns:
        Number of translation rows inserted.
    """
    db = SessionLocal()
    try:
        # Load only fields needed for EN backfill to avoid pulling large columns.
        props = db.execute(
            select(
                PropertyNormalized.id,
                PropertyNormalized.title,
                PropertyNormalized.description,
                PropertyNormalized.location_name,
            )
        ).all()
        if not props:
            print("No properties in database.")
            return 0

        # Existing en translations (map property_id -> translation row)
        result_existing = db.execute(
            select(PropertyTranslation).where(
                PropertyTranslation.language_code == "en"
            )
        )
        existing_en = {row.property_id: row for row in result_existing.scalars().all()}

        added = 0
        for prop_id, prop_title, prop_description, prop_location in props:
            address = (prop_location or "").strip() or None
            existing_row = existing_en.get(prop_id)

            # Existing EN row: backfill address when empty
            if existing_row is not None:
                has_address = (existing_row.address or "").strip()
                if not has_address and address:
                    if dry_run:
                        print(f"  [dry-run] would update en address for {prop_id}: address={address!r}")
                    else:
                        existing_row.address = address
                    added += 1
                continue

            # Missing EN row: create full translation row
            title = (prop_title or "").strip() or None
            description = (prop_description or "").strip() if prop_description else None
            if not title and not description and not address:
                title = "Untitled Property"
            if dry_run:
                print(f"  [dry-run] would add en translation for {prop_id}: title={title!r}")
                added += 1
                continue
            get_or_create_translation(
                db,
                property_id=prop_id,
                language_code="en",
                title=title,
                description=description,
                address=address,
            )
            added += 1

        if not dry_run and added:
            db.commit()
        return added
    finally:
        db.close()


def _translate_one_property(item: tuple) -> tuple:
    """Worker: (prop_id, en_title, en_desc, en_address) -> (prop_id, [(lang, title, desc, address), ...])."""
    prop_id, en_title, en_desc, en_address = item
    en_title = en_title or ""
    en_desc = en_desc or ""
    en_address = en_address or ""
    out = []
    for lang in ("ar", "esp", "fr"):
        t = translate_text(en_title, lang, "en") or en_title
        d = translate_text(en_desc, lang, "en") if en_desc else ""
        a = translate_text(en_address, lang, "en") if en_address else ""
        out.append((lang, t, d, a))
    return (prop_id, out)


def backfill_other_languages(
    dry_run: bool = False,
    batch_size: int = 100,
    workers: int = 8,
) -> int:
    """
    For each property that has an 'en' translation, create ar, esp, fr rows
    by translating title and description from en. Uses parallel workers to
    call the translation API; DB writes happen in the main thread.

    Returns:
            Number of translation rows added (ar + esp + fr per property).
    """
    db = SessionLocal()
    try:
        # Load (property_id, en title, en description) for all with en
        result = db.execute(
            select(
                PropertyNormalized.id,
                PropertyTranslation.title,
                PropertyTranslation.description,
                PropertyTranslation.address,
            ).join(
                PropertyTranslation,
                (PropertyTranslation.property_id == PropertyNormalized.id)
                & (PropertyTranslation.language_code == "en"),
            )
        )
        rows = result.all()
        if not rows:
            print("No properties with English translation found. Run backfill without --translate-other-languages first.")
            return 0

        if dry_run:
            print(f"  [dry-run] would translate {len(rows)} properties (ar, esp, fr)")
            return len(rows) * 3

        items = [(r[0], r[1], r[2], r[3]) for r in rows]
        added = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_translate_one_property, it): it for it in items}
            batch_results = []
            for i, future in enumerate(as_completed(futures)):
                prop_id, lang_tuples = future.result()
                batch_results.append((prop_id, lang_tuples))
                if (i + 1) % 500 == 0:
                    print(f"  Translated {i + 1}/{len(items)} (writing to DB in batches)...")
                if len(batch_results) >= batch_size:
                    for pid, lts in batch_results:
                        for lang, title, desc, address in lts:
                            get_or_create_translation(
                                db,
                                pid,
                                lang,
                                title=title or None,
                                description=desc or None,
                                address=address or None,
                            )
                            added += 1
                    db.commit()
                    print(f"  Committed: {added} translation rows so far.")
                    batch_results = []
            for pid, lts in batch_results:
                for lang, title, desc, address in lts:
                    get_or_create_translation(
                        db,
                        pid,
                        lang,
                        title=title or None,
                        description=desc or None,
                        address=address or None,
                    )
                    added += 1
        if added:
            db.commit()
        return added
    finally:
        db.close()


def show_translation_status() -> None:
    """Print property_translations counts by language so you can verify DB state."""
    db = SessionLocal()
    try:
        total = db.execute(select(func.count(PropertyTranslation.id))).scalar() or 0
        print("property_translations:")
        print(f"  total rows: {total}")
        for lang in ("en", "ar", "esp", "fr"):
            c = db.execute(
                select(func.count(PropertyTranslation.id)).where(
                    PropertyTranslation.language_code == lang
                )
            ).scalar() or 0
            print(f"  {lang}: {c}")
        prop_count = db.execute(select(func.count(PropertyNormalized.id))).scalar() or 0
        print(f"  (properties_normalized: {prop_count} properties)")
    finally:
        db.close()


def main():
    import argparse
    p = argparse.ArgumentParser(
        description="Backfill property_translations: en from DB; optionally ar, esp, fr via translation."
    )
    p.add_argument("--dry-run", action="store_true", help="Only print what would be done")
    p.add_argument(
        "--translate-other-languages",
        action="store_true",
        help="Create ar, esp, fr translations from en (parallel workers, faster)",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="Show property_translations counts by language and exit (no backfill)",
    )
    p.add_argument("--workers", type=int, default=8, help="Parallel workers for translation (default 8)")
    p.add_argument("--batch", type=int, default=100, help="Commit every N properties (default 100)")
    args = p.parse_args()

    if args.status:
        show_translation_status()
        return

    n_en = backfill_en_translations(dry_run=args.dry_run)
    print(f"English: added {n_en} translation(s).")
    if args.translate_other_languages:
        n_other = backfill_other_languages(
            dry_run=args.dry_run,
            batch_size=args.batch,
            workers=args.workers,
        )
        print(f"Other languages (ar, esp, fr): added {n_other} translation(s).")
    print("Done.")


if __name__ == "__main__":
    main()
