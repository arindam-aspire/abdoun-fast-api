# Abdoun FastAPI — Database Usage Report

**Project:** `abdoun_fast_api`  
**Report date:** July 13, 2026  
**Database:** PostgreSQL (`abdoun_internal_db_shared` / configurable via env)  
**Scope:** How the FastAPI backend uses the database today

---

## Executive Summary

The Abdoun FastAPI backend uses **synchronous SQLAlchemy 2.0** with **PostgreSQL** (psycopg2 driver). The application maps **45 database tables** but actively queries only **29 of them (64%)**. The remaining **16 tables (36%)** are mapped for schema compatibility but are **not used** by application code.

**Key findings:**

| Finding | Impact |
|---------|--------|
| Property data lives in `property_listing_submissions` (JSONB), not normalized property tables | 8 property-related tables are unused |
| `users` table is the most heavily used (14 files, 42 query references) | Core dependency for all domains |
| 16 tables have zero application queries | Schema bloat; potential cleanup or future integration |
| Legacy `properties` table (PostGIS) exists alongside the main catalog | Dual data model; CSV import only |
| No repository layer — routes and services query SQLAlchemy directly | Simple architecture; harder to optimize centrally |
| Several performance risks (in-memory filtering, N+1 queries) | Scalability concern as listings grow |

**Recommendation priority:** Focus optimization on `property_listing_submissions` and `users`; evaluate deprecating or integrating the 16 unused tables.

---

## Technology Stack

| Component | Details |
|-----------|---------|
| **Database** | PostgreSQL 17 |
| **ORM** | SQLAlchemy 2.0.34 (sync) |
| **Driver** | psycopg2-binary 2.9.9 |
| **Migrations** | Alembic 1.13.3 (HEAD: `0060_property_workflow_statuses`) |
| **Spatial (legacy)** | GeoAlchemy2 0.15.2 on `properties` table only |
| **Session pattern** | Request-scoped via FastAPI `Depends(get_db)` |
| **Not used** | SQLModel, asyncpg, repository pattern, async ORM |

### Connection Configuration

Environment variables (see `app/core/config.py`):

- `DATABASE_URL` — primary connection string
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — fallback URL builder
- `DB_SSLMODE` — default `require`

Default fallback: `postgresql+psycopg2://postgres:postgres@localhost:5432/realestate`

---

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐
│  API Routes │ ──► │   Services   │ ──► │  SQLAlchemy Models  │
│  (FastAPI)  │     │  (no repo)   │     │  (45 tables mapped) │
└─────────────┘     └──────────────┘     └──────────┬──────────┘
       │                                            │
       │ db.commit() on writes                      ▼
       └──────────────────────────────────►  PostgreSQL
```

- **Session injection:** `DBSessionDep` in `app/api/deps.py`
- **Transactions:** Explicit `db.commit()` in route handlers; no auto-commit middleware
- **Relationships:** Foreign keys defined on columns; no SQLAlchemy `relationship()` — joins are manual

---

## Table Usage Summary

### By status

| Status | Description | Count | % of 45 |
|--------|-------------|------:|--------:|
| **FULL** | Read and write in application | 17 | 37.8% |
| **READ-ONLY** | Queried but never written by API | 8 | 17.8% |
| **WRITE-ONLY** | Written but not read back via API | 3 | 6.7% |
| **LEGACY** | Used only in CSV import / dead code path | 1 | 2.2% |
| **UNUSED** | Mapped in SQLAlchemy; zero app queries | 16 | 35.6% |

### Read vs write (29 actively used tables)

| Metric | Total | Average per used table |
|--------|------:|----------------------:|
| Read references | 151 | 5.2 |
| Write references | 35 | 1.2 |
| Combined usage score | 186 | 6.4 |

*Usage score = count of read + write query patterns in `app/` and `scripts/` (excluding model definition files). Usage % is relative to `users` (100%).*

---

## Table-Wise Breakdown (All 45 Tables)

| # | Table | Status | App Files | Read | Write | Usage % | Notes |
|---|-------|--------|----------:|-----:|------:|--------:|-------|
| 1 | `users` | FULL | 14 | 39 | 3 | 100% | Auth, agents, owners, leads — core table |
| 2 | `property_listing_submissions` | FULL | 7 | 21 | 3 | 57% | **Primary property catalog** (JSONB payload) |
| 3 | `agency_master` | FULL | 8 | 18 | 2 | 48% | Agency registration, review, activation |
| 4 | `agent_profiles` | FULL | 2 | 9 | 3 | 29% | Agent onboarding and status |
| 5 | `roles` | FULL | 5 | 10 | 1 | 26% | RBAC role definitions |
| 6 | `user_roles` | FULL | 5 | 9 | 1 | 24% | User ↔ role assignments |
| 7 | `agency_invitations` | FULL | 1 | 4 | 1 | 12% | Agency invite workflow |
| 8 | `agent_invites` | FULL | 1 | 3 | 2 | 12% | Agent invite workflow |
| 9 | `notifications` | FULL | 2 | 3 | 2 | 12% | In-app notifications |
| 10 | `property_deal_closures` | FULL | 2 | 4 | 1 | 12% | Deal closure requests/reviews |
| 11 | `property_categories` | READ-ONLY | 3 | 5 | 0 | 12% | Taxonomy — public catalog |
| 12 | `property_types` | READ-ONLY | 3 | 5 | 0 | 12% | Taxonomy — public catalog |
| 13 | `recently_viewed_properties` | FULL | 1 | 1 | 4 | 12% | User recent views |
| 14 | `user_agency_mappings` | FULL | 2 | 4 | 1 | 12% | Multi-agency user links |
| 15 | `user_property_favorites` | FULL | 2 | 3 | 2 | 12% | User favorites |
| 16 | `leads` | FULL | 3 | 3 | 1 | 10% | Lead management |
| 17 | `user_profile_change_challenges` | FULL | 2 | 2 | 2 | 10% | OTP, password setup |
| 18 | `user_saved_searches` | FULL | 1 | 2 | 2 | 10% | Saved search CRUD |
| 19 | `properties` | LEGACY | 2 | 3 | 1 | 10% | PostGIS legacy; CSV import only |
| 20 | `areas` | READ-ONLY | 3 | 3 | 0 | 7% | Location taxonomy |
| 21 | `cities` | READ-ONLY | 2 | 3 | 0 | 7% | Location taxonomy |
| 22 | `activity_logs` | FULL | 2 | 1 | 1 | 5% | Audit trail (admin read) |
| 23 | `features` | READ-ONLY | 2 | 2 | 0 | 5% | Feature catalog |
| 24 | `notification_preferences` | READ-ONLY | 1 | 1 | 0 | 2% | Read-only; no update API |
| 25 | `permissions` | READ-ONLY | 1 | 1 | 0 | 2% | Auth permission checks |
| 26 | `role_permissions` | READ-ONLY | 1 | 1 | 0 | 2% | Role ↔ permission join |
| 27 | `lead_messages` | WRITE-ONLY | 1 | 0 | 1 | 2% | Stored on POST; not returned in GET |
| 28 | `lead_notes` | WRITE-ONLY | 1 | 0 | 1 | 2% | Stored on POST; not returned in GET |
| 29 | `lead_status_history` | WRITE-ONLY | 1 | 0 | 1 | 2% | Audit trail; no history API |
| 30 | `admin_agent_assignments` | UNUSED | 0 | 0 | 0 | 0% | — |
| 31 | `category_features` | UNUSED | 0 | 0 | 0 | 0% | — |
| 32 | `category_search_fields` | UNUSED | 0 | 0 | 0 | 0% | — |
| 33 | `dashboard_summary` | UNUSED | 0 | 0 | 0 | 0% | — |
| 34 | `lead_number_counters` | UNUSED | 0 | 0 | 0 | 0% | App counts leads instead |
| 35 | `owner` | UNUSED | 0 | 0 | 0 | 0% | Owners = `users` with role |
| 36 | `property_features` | UNUSED | 0 | 0 | 0 | 0% | Data in JSONB payload |
| 37 | `property_media` | UNUSED | 0 | 0 | 0 | 0% | Data in JSONB payload |
| 38 | `property_owner` | UNUSED | 0 | 0 | 0 | 0% | Data in JSONB payload |
| 39 | `property_status` | UNUSED | 0 | 0 | 0 | 0% | JSON config used instead |
| 40 | `property_translations` | UNUSED | 0 | 0 | 0 | 0% | Data in JSONB payload |
| 41 | `property_views` | UNUSED | 0 | 0 | 0 | 0% | — |
| 42 | `search_fields` | UNUSED | 0 | 0 | 0 | 0% | — |
| 43 | `social_accounts` | UNUSED | 0 | 0 | 0 | 0% | — |
| 44 | `type_features` | UNUSED | 0 | 0 | 0 | 0% | — |
| 45 | `user_remember_me_sessions` | UNUSED | 0 | 0 | 0 | 0% | — |

---

## Domain-Level View

| Domain | Fully Used | Partial | Unused |
|--------|:----------:|:-------:|:------:|
| Auth & users | 4 | 3 | 2 |
| Agency | 3 | 0 | 1 |
| Agents | 2 | 0 | 0 |
| Properties | 2 | 2 | 8 |
| Taxonomy | 0 | 5 | 4 |
| Leads | 1 | 4 | 0 |
| User features | 3 | 0 | 0 |
| Notifications | 1 | 1 | 0 |
| Audit | 1 | 0 | 1 |

---

## API Endpoints with Database Access

| Domain | Key Endpoints | Primary Tables |
|--------|---------------|----------------|
| Auth | `POST /auth/login`, `/signup`, `GET /auth/me` | `users`, `user_roles`, `roles` |
| Agency | `POST /agency/register`, `GET /agency/list` | `agency_master`, `agency_invitations` |
| Agents | `POST /agents/invite`, `GET /agents` | `agent_invites`, `agent_profiles`, `users` |
| Properties (public) | `GET /properties`, `GET /properties/{id}` | `property_listing_submissions` |
| Property submissions | `POST /property-submissions`, `PATCH /{id}` | `property_listing_submissions` |
| Leads | `POST /leads`, `GET /leads`, `PATCH /{id}/status` | `leads`, `lead_notes`, `lead_messages` |
| Favorites | `GET/POST/DELETE /favorites` | `user_property_favorites` |
| Saved searches | Full CRUD `/saved-searches` | `user_saved_searches` |
| Notifications | `GET /notifications`, `PUT /read-all` | `notifications` |
| Deal closures | `POST/GET /deal-closures` | `property_deal_closures` |
| Catalog | `GET /features`, `/property-taxonomy` | `features`, `property_categories`, `property_types`, `cities`, `areas` |
| Audit | `GET /audit-logs` | `activity_logs` |
| CSV import | `POST /import-csv` | `properties` (legacy PostGIS) |

---

## Migrations (Alembic)

| Revision | Purpose |
|----------|---------|
| `0001`–`0003` | Legacy `properties` PostGIS table |
| `0053` | No-op baseline (live DB already had schema) |
| `0054` | `property_deal_closures` |
| `0055` | `user_agency_mappings` |
| `0056`–`0060` | Taxonomy seeds, property workflow statuses |

**Head revision:** `0060_configurable_property_workflow_statuses`

---

## Identified Risks & Improvement Opportunities

### High priority

| Issue | Affected tables | Recommendation |
|-------|-----------------|----------------|
| In-memory property filtering | `property_listing_submissions` | Move filter/sort/pagination to SQL |
| N+1 deal-closure checks | `property_deal_closures` | Batch check in one query per request |
| Taxonomy reloaded per listing | `property_categories`, `property_types`, `cities`, `areas` | Cache per request or use TTL cache |
| 16 unused tables | See list above | Decide: integrate, deprecate, or document as external-only |

### Medium priority

| Issue | Recommendation |
|-------|----------------|
| Lead notes/messages not exposed on read | Add to `GET /leads/{id}` or document as intentional |
| `lead_number_counters` bypassed | Use counter table for atomic lead numbering |
| `property_status` table unused | Wire to API or remove from active schema |
| Legacy `properties` vs `property_listing_submissions` | Consolidate or clearly separate purposes |
| No explicit rollback on write failures | Add `db.rollback()` in error handlers |

### Low priority

| Issue | Recommendation |
|-------|----------------|
| `notification_preferences` read-only | Add update endpoint if product needs it |
| Duplicate `DBSessionDep` in `search.py` | Import from `deps.py` for consistency |

---

## Quick Reference

```text
Database:     PostgreSQL (abdoun_internal_db_shared)
ORM:          SQLAlchemy 2.0 + psycopg2 (sync)
Tables:       45 mapped | 29 used (64%) | 16 unused (36%)
Core table:   property_listing_submissions (main catalog)
Legacy table: properties (PostGIS, CSV import only)
Migrations:   Alembic — HEAD 0060
Pattern:      Routes → Services → SQLAlchemy (no repository layer)
```

---

## Appendix: Unused Tables (Full List)

These 16 tables are defined in the database and mapped in `app/models/live_schema.py` but have **no queries** in application or script code:

1. `admin_agent_assignments`
2. `category_features`
3. `category_search_fields`
4. `dashboard_summary`
5. `lead_number_counters`
6. `owner`
7. `property_features`
8. `property_media`
9. `property_owner`
10. `property_status`
11. `property_translations`
12. `property_views`
13. `search_fields`
14. `social_accounts`
15. `type_features`
16. `user_remember_me_sessions`

**Likely reason:** The product stores property media, features, owners, and translations inside the `property_listing_submissions.payload` JSONB column rather than in normalized relational tables.

---

*Report generated from static analysis of `abdoun_fast_api` application code. For live schema details, see `docs/phase0/Live_DB_Schema_Inventory.md`.*
