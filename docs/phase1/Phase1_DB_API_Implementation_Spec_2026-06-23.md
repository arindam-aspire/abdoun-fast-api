# Phase 1 DB/API Implementation Specification

Date: 2026-06-23  
Branch: `feature/autonomous-remaining-development`  
Repository: `abdoun_fast_api`

## Phase 1 Objective

Align the backend application code with the existing live demo database schema so later phases can implement business workflows without duplicating tables or applying unsafe migrations.

The connected database is confirmed by the project owner as a test/demo database. Schema and data changes are permitted when required for development. Even with that permission, changes should be made through tracked Alembic migrations, repeatable scripts, or committed seed utilities rather than one-off manual mutation.

Phase 1 is a backend foundation phase. It does not finish the full product workflow. It prepares the application for phases 2-10 by establishing:

- reliable DB connection handling
- local code awareness of the live DB schema
- SQLAlchemy model coverage for existing foundational tables
- safe Alembic migration strategy from the live DB head
- shared API conventions for pagination, errors, auth dependency placeholders, audit, notification, and localization-aware responses

## Authoritative Phase 0 Evidence

Live schema inventory:

- `docs/phase0/Live_DB_Schema_Inventory.md`
- `docs/phase0/live_db_schema_inventory.json`

Connection checks:

```powershell
python scripts\inspect_db_schema.py --markdown docs\phase0\Live_DB_Schema_Inventory.md --json docs\phase0\live_db_schema_inventory.json
python scripts\check_app_db_connection.py
```

Successful outputs:

```text
db-schema-inspection-ok
schemas=1
tables=42
```

```text
app-db-connection-ok
database=abdoun_internal_db_shared
```

Live DB facts:

| Item | Value |
| --- | --- |
| Schema | `public` |
| Table count | 42 |
| Live Alembic version | `0053_owner_soft_delete` |
| PostgreSQL extensions | `plpgsql` |
| Enum types | `lead_message_channel_enum`, `lead_source_enum`, `lead_status_enum`, `property_view_user_type` |

## Critical Alignment Findings

### Existing backend code is behind the live DB

The repository currently has only a narrow seed implementation:

- model: `Property`
- table expected by code: `properties`
- routes: health, property list/detail, spatial search, CSV import
- local migrations: `0001_create_properties`, `0002_add_integer_id`, `0003_add_location_name`

The live database is already at Alembic revision `0053_owner_soft_delete` and contains tables for:

- users and roles
- agency master
- agent profiles and invitations
- property listing submissions
- property taxonomy
- property media/features/translations/status
- owners
- leads, messages, notes, and status history
- notifications and preferences
- favorites, recent views, saved searches
- dashboard and audit/activity data

### `properties` table mismatch

The current backend code expects a `properties` table, but the generated live schema inventory does not list `public.properties`.

Several live tables still contain `property_id` columns, but many are not declared as foreign keys to a discovered `properties` table.

Phase 1 must not assume the current `Property` model is correct. Before restoring or replacing public property APIs, implementation must verify the intended canonical property source:

- `property_listing_submissions.payload`
- missing/legacy `properties` table
- another property table not currently visible
- a view expected to be created by a missing migration

Until that is resolved in code, property list/detail endpoints should not silently rely on the stale local model.

### Alembic lineage mismatch

Local migration files stop at `0003_add_location_name`, while the live DB reports `0053_owner_soft_delete`.

Phase 1 migration strategy:

1. Add a local baseline Alembic revision for `0053_owner_soft_delete` so the repository can recognize the live DB head.
2. Do not run the old `0001`-`0003` migrations against the live demo DB.
3. New schema changes must be authored as revisions after the recognized `0053_owner_soft_delete` baseline.
4. Future migrations may be applied to the authorized test DB, but they must be committed and validated before moving phases.
5. Destructive data cleanup is allowed only when it supports a phase gate and should be captured in a script or documented command.

Implementation note:

- If keeping legacy `0001`-`0003` migrations creates multiple Alembic heads or an unsafe graph, archive or isolate them deliberately with documentation rather than letting Alembic apply them accidentally.

## Live Table Groups

### Identity and Access

Tables:

- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`
- `social_accounts`
- `user_remember_me_sessions`
- `user_profile_change_challenges`

Phase 1 model coverage:

- Create SQLAlchemy models matching columns and relationships.
- Add role constants for `Super Admin`, `Agency Admin`, agent, property owner, and end user naming used by existing data.
- Add reusable auth dependency placeholders that can be completed in Phase 2.

### Agency and Agent Foundation

Tables:

- `agency_master`
- `agent_profiles`
- `agent_invites`
- `admin_agent_assignments`

Phase 1 model coverage:

- Model agency ownership and user agency scoping.
- Model agent profile status fields and review metadata.
- Keep operational workflows for Phase 2 and Phase 3.

### Property Foundation

Tables:

- `property_listing_submissions`
- `property_categories`
- `property_types`
- `property_status`
- `property_features`
- `property_media`
- `property_translations`
- `property_owner`
- `owner`
- `features`
- `category_features`
- `type_features`
- `search_fields`
- `category_search_fields`
- `cities`
- `areas`

Phase 1 model coverage:

- Model the existing tables exactly.
- Treat `property_listing_submissions.payload` as the likely draft/submission data source until canonical active-property storage is verified.
- Include multilingual support via `property_translations.language_code`.
- Preserve configured document extensibility for later phases; exact document type lists are still business-configurable.

### Leads and Deal Preparation

Tables:

- `leads`
- `lead_messages`
- `lead_notes`
- `lead_status_history`
- `lead_number_counters`

Phase 1 model coverage:

- Model current lead statuses and enum values.
- Record that BRD-confirmed `Connected` is not present in the live `lead_status_enum` and must be handled in a later migration/spec decision.
- Preserve separate lead closure and property deal closure concepts for Phase 6 and Phase 7.

### Notifications and Audit

Tables:

- `notifications`
- `notification_preferences`
- `activity_logs`

Phase 1 model coverage:

- Model in-app notification polling requirements.
- Keep email/SMS provider abstraction as log-only for current dev/demo mode.
- Keep audit/activity logging reusable across phases.

### User Property Interactions

Tables:

- `user_property_favorites`
- `recently_viewed_properties`
- `property_views`
- `user_saved_searches`
- `dashboard_summary`

Phase 1 model coverage:

- Model user-property interaction tables.
- Defer saved-search matching notifications because they are out of MVP.

## Phase 1 API Foundation Scope

Phase 1 should create common backend building blocks, not full feature endpoints.

Required foundation:

- `app/models/*` split by domain instead of one stale property model only
- `app/schemas/common.py` for pagination and standard response metadata
- `app/api/deps.py` or equivalent for DB session, current-user placeholder, role checks, and agency scoping helpers
- `app/services/audit.py` for writing `activity_logs`
- `app/services/notifications.py` with in-app persistence and email/SMS log-mode provider stubs
- `app/core/localization.py` for supported language constants and English fallback
- `app/core/security.py` or equivalent for password hashing/token primitives if not already present
- route modules can be scaffolded but should avoid incomplete business behavior beyond the phase

Required config additions:

| Setting | Purpose | Default |
| --- | --- | --- |
| `DB_SSLMODE` | Explicit DB SSL mode | `require` |
| `NOTIFICATION_EMAIL_MODE` | Email provider mode | `log` |
| `NOTIFICATION_SMS_MODE` | SMS provider mode | `log` |
| `NOTIFICATION_POLL_INTERVAL_SECONDS` | In-app polling default | `30` |
| `SUPPORTED_LOCALES` | App locales | `en,ar,fr,es` |
| `DEFAULT_LOCALE` | Fallback locale | `en` |

## Phase 1 Non-Goals

Do not complete these in Phase 1:

- agency onboarding workflow screens
- agent invitation end-to-end flow
- property approval/revision workflow
- public property search replacement
- lead workflow
- deal closure workflow
- notification UI integration
- frontend changes

Those are later phase deliverables.

## Phase 1 Test Gate

Before Phase 1 is committed:

1. `python -m compileall app scripts`
2. `python scripts\check_app_db_connection.py`
3. `python scripts\inspect_db_schema.py --markdown docs\phase0\Live_DB_Schema_Inventory.md --json docs\phase0\live_db_schema_inventory.json`
4. Alembic must be able to recognize the live DB current revision without trying to apply legacy migrations.
5. Any new unit tests added for common services must pass.

## Phase 1 Commit Gate

Commit only after:

- generated or updated models compile
- DB connection check passes
- live schema inventory remains readable
- Alembic baseline strategy is documented in code/docs
- no unrelated frontend/shared-library files are modified

## Open Technical Decisions for Phase 1 Implementation

These must be resolved during implementation using code and DB evidence:

| Decision | Required Resolution |
| --- | --- |
| Canonical active property source | Determine whether active properties come from a missing table, a payload projection, or a view |
| Alembic local graph | Decide whether to archive legacy 0001-0003 migrations or connect them to the 0053 baseline safely |
| Lead `Connected` status | Add migration later or map to existing statuses only after confirming business impact |
| Property documents | Reuse payload/doc metadata or add configurable document tables in Phase 4 |
| Deal closure persistence | Confirm whether existing schema has no dedicated deal closure table and add in Phase 7 if needed |

## Phase 1 Delivery Summary

Phase 1 should end with the backend codebase accurately reflecting the current DB foundation and ready for feature implementation. The key outcome is not new user-facing behavior; it is preventing the remaining phases from being built on stale local assumptions.
