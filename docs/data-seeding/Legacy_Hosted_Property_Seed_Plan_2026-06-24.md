# Legacy Hosted Property Seed Plan - 2026-06-24

## Source

- Hosted MLS site: `https://main.d2z0ffrg8gzslv.amplifyapp.com`
- Public API discovered from hosted bundle: `https://dev-api-abdn.wpsitedesigner.com/api/v1`
- Seed script: `scripts/seed_legacy_hosted_properties.py`

## Target

- Current backend database configured by `abdoun_fast_api/.env`.
- Existing target DB before seed check: 78 property submissions, 15 approved public listings.

## Seed Scope

The seed is intentionally limited to a QA-friendly subset instead of copying the full legacy dataset.

| Segment | Target Count |
| --- | ---: |
| Residential buy - villa | 12 |
| Residential buy - apartment | 12 |
| Residential rent - villa | 12 |
| Residential rent - apartment | 12 |
| Commercial buy | up to 6 |
| Commercial rent | up to 4 |
| Land buy | up to 8 |

The script fetches extra records per segment and prioritizes records with media when available.
Each seeded listing stores at most 8 images to keep API payloads and frontend galleries performant.

## Mapping Rules

- Records are inserted as approved `property_listing_submissions`.
- `status=buy` maps to `basic_information.listing_purpose = sale`.
- `status=rent` maps to `basic_information.listing_purpose = rent`.
- Category is taken from the seed segment, not blindly from the legacy record, because legacy commercial records may serialize as `residential`.
- Property type is matched to current DB taxonomy by slug/name with fallbacks:
  - Residential fallback: `apartment`
  - Commercial fallback: `office`
  - Land fallback: `land`
- City/area are matched by name against current taxonomy, with Amman/first area fallback.
- Media URLs are stored without query strings. The current backend response layer signs S3 URLs at read time, so public images should not be broken.
- Each seeded record stores `_seed.source = legacy-hosted-dev-api` and `_seed.source_id`.
- Existing `property_id` and existing seed source IDs are skipped to avoid duplicates.
- Existing matching legacy records that are already approved are left untouched.
- Existing matching legacy records that are submitted/rejected are updated to approved with the seed marker instead of inserting a duplicate public property ID.

## Validation Plan

1. Dry-run the seed script and review counts by segment.
2. Insert only if the dry run produces valid planned rows.
3. Verify local API returns expected increased counts for:
   - `category=residential&status=buy`
   - `category=residential&status=rent`
   - `category=commercial&status=buy`
   - `category=commercial&status=rent`
   - `category=land&status=buy`
4. Verify returned media URLs are signed by the current backend and at least one seeded media URL loads with HTTP 200.

## Execution Result

Executed against the current `.env` database on 2026-06-24.

Dry-run summary:

```text
fetched: 60
skipped_existing_approved: 6
planned_inserts: 39
planned_updates: 15
planned_total: 54
with_media: 49
```

Inserted/updated:

```text
inserted: 39
updated: 15
submitter: amondal@coderlook.com
```

Post-seed public API validation:

| Query | Total |
| --- | ---: |
| `category=residential&status=buy` | 17 |
| `category=residential&status=rent` | 19 |
| `category=commercial&status=buy` | 3 |
| `category=commercial&status=rent` | 1 |
| `category=land&status=buy` | 8 |

Database validation:

```text
approved_total: 69
seeded_marked: 54
```

Media validation:

- Representative seeded image URLs returned `200 image/jpeg`.
- Non-S3 public Abdoun media URLs are intentionally not presigned.
- S3 URLs continue to be presigned by the backend media URL response layer.

## Rollback

If rollback is needed, delete records where:

```sql
payload->'_seed'->>'source' = 'legacy-hosted-dev-api'
```
