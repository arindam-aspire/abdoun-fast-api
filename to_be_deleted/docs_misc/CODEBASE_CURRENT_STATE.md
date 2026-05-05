# Current Codebase State

This document captures the **current implemented state** of the repository for onboarding, maintenance, and refactor planning.

## 1) High-level system

- **Backend framework:** FastAPI (`app/main.py`)
- **Data layer:** PostgreSQL + SQLAlchemy + Alembic migrations
- **API versioning:** v1 mounted at `settings.api_v1_prefix` (default `/api/v1`)
- **Architecture style:** mostly `Route -> Service -> Repository -> DB`
- **Primary domains:** authentication/RBAC, property catalog/search, agent/admin workflows, submissions moderation, media uploads, saved/favorite/recent views

## 2) Runtime composition

### App bootstrap (`app/main.py`)

- Creates FastAPI app and includes v1 router.
- Registers middleware:
  - request correlation id
  - security headers
  - CORS
  - optional Prometheus middleware
- Registers rate limit handler (`slowapi`).
- Enables optional observability:
  - Sentry
  - OpenTelemetry
- Exposes:
  - `GET /health`
  - optional metrics endpoint (`settings.metrics_path`)
- Starts optional dashboard summary scheduler on lifespan startup.

### API aggregation (`app/api/v1/router.py`)

Mounted router modules:

- `auth`, `agent`, `agents`, `admin`, `admin_properties`
- `users`, `owners`, `favorites`, `saved_searches`, `recent_views`
- `property_submissions`, `admin_property_submissions`
- `uploads`, `agent_properties`
- `properties`, `search`, `locations`, `property_taxonomy`

## 3) Code organization (current)

- `app/api/v1/routes/` -> HTTP handlers and transport mapping
- `app/api/v1/deps/` -> dependency providers (service/repository/session wiring)
- `app/services/` -> business/application logic
- `app/repositories/` -> persistence operations
- `app/models/` -> SQLAlchemy models
- `app/schemas/` -> request/response schemas
- `app/middleware/` -> request/response middleware
- `app/observability/` -> tracing, sentry, slow query helpers
- `app/schedulers/` -> scheduled tasks
- `scripts/` -> operational and data-management scripts
- `tests/` -> unit, validation, and API contract coverage

## 4) Main implemented capabilities

- **Authentication & identity**
  - signup/confirm/resend, password login, OTP login, refresh/logout
  - forgot/reset password and profile update verification flows
  - social login callback flow
- **Authorization**
  - role checks and permission checks in API dependencies
  - user-role management endpoints under `/users`
- **Property discovery**
  - list/filter properties, property details, similar properties
  - geo-search by bounds/polygon
  - location taxonomy and property taxonomy endpoints
- **User personalization**
  - favorites CRUD
  - saved searches CRUD and execute
  - recent views add/list/remove/clear
- **Submission workflow**
  - draft/create/patch/submit/delete for agents
  - admin moderation/review/approve/reject flows
  - admin direct submit-and-approve flows
- **Agent/admin workflows**
  - invite/onboard/manage agents
  - assignment and dashboard metrics
  - property assignment to agent by admin
- **Media uploads**
  - presigned upload URL generation
  - profile picture upload workflow with URL signing
- **Data operations**
  - CSV import pipeline, backfills, RBAC seed/verify scripts

## 5) Config and environment model

`app/core/config.py` defines env-driven settings for:

- database URL + pool settings
- CORS configuration
- AWS Cognito and S3
- OTP/profile settings
- observability toggles (metrics, OTEL, Sentry)
- scheduler toggle and schedule time

## 6) Testing state

Current `tests/` includes:

- **Unit tests:** services, repositories, middleware, utils, core config/security
- **API tests:** route/dependency behavior checks
- **Validation tests:** architecture guardrails (e.g., no DB access in routers)
- **Contract tests:** endpoint contract expectations and coverage checks

This provides a useful baseline for safe incremental refactors.

## 7) Operational artifacts

- **Migrations:** `alembic/versions`
- **Scripts:** import/backfill/seed/check/test utilities in `scripts/`
- **Data:** sample/input CSV in `data/`
- **Infra files:** `Dockerfile`, `docker-compose.yml`, env templates

## 8) Existing documentation map

Already available docs include:

- `docs/API_V1_ENDPOINT_CATALOG.md` (endpoint inventory)
- `docs/API_SOLID_ARCHITECTURE_REVIEW.md` (architecture quality review)
- `docs/VIBE_CODING_POLICY.md` (engineering/refactor policy)
- authentication, testing, integration, and Cognito-focused docs

## 9) Known codebase notes for future refactor

- There are duplicate path variants visible in listing results (e.g. mixed slash/case paths); normalize imports/paths carefully during cleanup.
- Several modules carry compatibility behavior for older clients; preserve behavior unless explicitly migrating clients.
- Keep refactors phased: test parity first, then structural improvements.

