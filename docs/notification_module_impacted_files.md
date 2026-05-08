# Final Notification Module — Impacted Files & Implementation Specification (Phase 1)

## Project Context

This document defines the implementation-ready specification for the **Notification Module Phase 1** for the Abdoun Real Estate platform.

This document is aligned with:

- Existing FastAPI architecture
- Existing repository/service patterns
- Current BRD requirements
- Existing authentication and RBAC implementation
- Existing Lead and Agent workflows

This document focuses ONLY on:

- In-App Notifications
- Notification Persistence
- Notification APIs
- Read/Unread Management
- Notification Preferences
- Notification Center APIs
- Polling-based notification updates

This document excludes all future notification delivery channels.

It is based on a scan of the current codebase (notably: `app/services/notification.py`, `app/api/v1/router.py`, `app/models/user.py`, `app/services/translation_service.py`, and Alembic setup under `alembic/`).

---

## 1. Current Phase Scope

### Included in Phase 1

- In-App Notifications
- Notification Persistence
- Notification APIs
- Read/Unread Management
- Notification Preferences
- Notification Center APIs
- Notification Trigger Integration
- Polling-based notification updates

### Excluded from Phase 1

- Email Notifications
- SMS Notifications
- Push Notifications
- Queue Workers / Async Delivery
- WebSocket/SSE Realtime
- Delivery Tracking / Retry Mechanisms
- Third-party notification providers
- Notification scheduling / background workers

---

## 2. Architecture Decisions (ADR)

1. Notifications are persisted directly in PostgreSQL.
2. Notification creation happens inside service layer only.
3. No queue or worker system in Phase 1.
4. No websocket/realtime support in Phase 1.
5. Notification messages are template-driven using constants.
6. Notifications use soft archive strategy (no hard deletes).
7. APIs are polling-based.
8. Architecture must remain extensible for Email/SMS/Push.
9. Notification APIs must enforce strict ownership validation.
10. Notification logic must remain centralized.

---

## 3. Notification Lifecycle

Lifecycle flow:

```text
CREATED
    ↓
UNREAD
    ↓
READ
    ↓
ARCHIVED
```

Lifecycle rules:

- New notifications are always created as unread.
- Marking notification as read:
  - sets `is_read = true`
  - sets `read_at = current_timestamp`
- Archived notifications:
  - are excluded from default inbox APIs
  - remain stored in database
- Notifications are never physically deleted in Phase 1.

---

## Summary of what exists today

- **Existing notification implementation is minimal**: `app/services/notification.py` only logs agent approval/rejection/invite events (no DB tables, no APIs, no preferences, no queue, no realtime).
- **Migrations framework exists**: Alembic is set up (`alembic/env.py`) and models are exported via `app/db/base.py`.
- **Translations exist for properties**: `app/services/translation_service.py` and `property_translations` patterns exist (en/ar/esp/fr), which can be mirrored for notifications.
- **User language is not present yet**: no `preferred_language` field was found in the repo (search returned no matches).
- **No queue / realtime stack found**: no WebSocket or queue libraries were detected by search (no `WebSocket`, `celery`, `rabbit`, `sqs`, etc.).

---

## 4. Notification Trigger Matrix (Phase 1)

| Event | Trigger Location | Recipient |
| --- | --- | --- |
| Lead Created | `LeadService.create_lead()` | Assigned Agent |
| Lead Assigned | `LeadService.assign_lead()` | Assigned Agent |
| Lead Reassigned | `LeadService.reassign_lead()` | New Agent |
| Lead Status Changed | `LeadService.update_status()` | Agent + Admin |
| Lead Reply Added | `LeadService.reply_to_lead()` | Assigned Agent |
| Agent Approved | `AgentService.approve_agent()` | Agent |
| Agent Rejected | `AgentService.reject_agent()` | Agent |
| System Announcement | Admin Panel | All Users |
| Profile Updated | `ProfileService.update_profile()` | User |

---

## 5. Existing files to modify

### API routing

- `app/api/v1/router.py`
  - Include the new routers for:
    - `/notifications`
    - `/notification-settings`
  - Phase 1 note: **no websocket**; polling only.

- `app/utils/constants.py`
  - Add `ApiRoutes` entries (prefix + tag) for the new notification endpoints.

### Database model exports (Alembic autogenerate visibility)

- `app/db/base.py`
  - Export the new notification ORM models so Alembic detects them in `target_metadata`.

### User language preference (BRD multilingual requirement)

- `app/models/user.py`
  - Add `preferred_language` (or `language_code`) to support:
    - “Fetch user's preferred language from users table” (BRD section 23).

### Existing notification service (currently logging only)

- `app/services/notification.py`
  - Either:
    - expand into a full notification service layer, **or**
    - keep it for agent onboarding logs and introduce a new dedicated module service (recommended).

### Event trigger points (emit notification events)

These files/areas will need updates to **create** in-app notifications for Phase 1 flows:

- `app/api/v1/routes/auth.py` and/or `app/services/auth_service.py`
  - Phase 1 note: OTP / Email / SMS delivery is excluded, but **system events** can still create in-app notifications (e.g. login alert) if desired.

- `app/services/profile_update_service.py`
  - Profile OTP delivery mentions the auth OTP path; will likely need notification logging/settings enforcement consistency.

- Lead and property flows (Phase 1 focus: lead + agent onboarding + system announcements + profile update)
  - Files are expected under `app/services/lead_*` and property submission/admin flows (e.g. `app/services/property_submission_service.py`).
  - Specific emit points will be mapped when implementing each BRD “Notification Type” event.

---

## 6. New files to add (Phase 1; aligned to this repo)

Folder alignment:

- The BRD suggests `src/modules/notifications/...`.
- This repo uses `app/...`.
- Phase 1 will add files under `app/...` in the same patterns you already use (`models/`, `repositories/`, `services/`, `schemas/`, `api/v1/routes/`, `api/v1/deps/`).

### ORM models

- `app/models/notification.py`
  - Main notification entity (inbox + read/unread + archive)

- `app/models/notification_preference.py`
  - User notification preferences (Phase 1)

### Alembic migrations

- `alembic/versions/xxxx_create_notifications_table.py`
- `alembic/versions/xxxx_create_notification_preferences_table.py`
- `alembic/versions/xxxx_add_user_language_column.py`

### API routes (FastAPI)

- `app/api/v1/routes/notifications.py`
  - `GET /notifications`
  - `GET /notifications/unread-count`
  - `PUT /notifications/{id}/read`
  - `PUT /notifications/read-all`
  - `POST /notifications/{id}/archive` (Phase 1: archive instead of delete)

- `app/api/v1/routes/notification_settings.py`
  - `GET /notification-settings`
  - `PUT /notification-settings`

### Schemas (Pydantic)

- `app/schemas/notifications.py`
- `app/schemas/notification_settings.py`
- (optional) `app/schemas/device_tokens.py`

### Repositories

- `app/repositories/notification_repository.py`
- `app/repositories/notification_preferences_repository.py`

### Services

- `app/services/notification_service.py`
  - Centralized orchestration:
    - create notification
    - validate ownership
    - list notifications
    - unread count
    - mark read / mark all read
    - archive

- `app/services/notification_preference_service.py`
  - get/update preferences
  - enforce Phase 1 rules:
    - system notifications cannot be disabled
    - marketing notifications can be disabled

- `app/services/notification_template_service.py`
  - template-driven titles/messages using constants
  - placeholder replacement
  - future localization ready

### Dependency wiring

- `app/api/v1/deps/notifications.py`
  - construct repositories/services and inject into routes

### Constants (templates + event registry)

- `app/constants/notification_types.py`
- `app/constants/notification_messages.py`

---

## 7. Phase 1 Database Design

### `notifications` table

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY,

    recipient_user_id UUID NOT NULL,
    actor_user_id UUID NULL,

    type_key VARCHAR(100) NOT NULL,

    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,

    data JSONB NULL,

    is_read BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    read_at TIMESTAMP NULL,
    archived_at TIMESTAMP NULL,

    FOREIGN KEY (recipient_user_id) REFERENCES users(id),
    FOREIGN KEY (actor_user_id) REFERENCES users(id)
);
```

### `notification_preferences` table

```sql
CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    notification_type VARCHAR(100) NOT NULL,

    enabled BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 8. Required Database Indexes

```sql
CREATE INDEX idx_notifications_recipient
ON notifications(recipient_user_id);

CREATE INDEX idx_notifications_unread
ON notifications(recipient_user_id, is_read);

CREATE INDEX idx_notifications_created
ON notifications(created_at DESC);
```

---

## 9. Notification Payload Contract

Standard payload structure:

```json
{
  "entity_type": "lead",
  "entity_id": "uuid",
  "action_url": "/leads/123",
  "metadata": {
    "lead_name": "John Doe"
  }
}
```

Rules:

- Payload must remain lightweight.
- Avoid storing sensitive data.
- Avoid large nested objects.

---

## 10. API Response Contract

Notification DTO:

```json
{
  "id": "uuid",
  "type_key": "lead.assigned",
  "title": "New Lead Assigned",
  "message": "A lead has been assigned to you",
  "is_read": false,
  "created_at": "ISO_DATETIME",
  "read_at": null,
  "data": {}
}
```

---

## 11. Pagination Rules

- Strategy: `LIMIT` + `OFFSET`
- Default page size: `20`
- Maximum page size: `100`
- Sort: `created_at DESC`

---

## 12. Ownership Validation Rules

Mandatory rule:

```python
notification.recipient_user_id == current_user.id
```

Security requirements:

- Users can only access their own notifications.
- Users can only modify their own notifications.
- Users cannot archive notifications belonging to others.
- Notification APIs require authenticated JWT user.

---

## 13. Logging & Observability (Phase 1)

Every notification creation must log:

- `notification_id`
- `type_key`
- `recipient_user_id`
- `actor_user_id`
- `request_id`

This aligns with existing request ID middleware patterns in this codebase.

---

## 14. Error Handling Rules

- `400` → Invalid request
- `401` → Unauthorized
- `403` → Forbidden
- `404` → Notification not found
- `500` → Internal server error

---

## 15. Testing Requirements

Required coverage:

- Unit tests
- Integration tests
- Ownership validation tests
- Read/unread tests
- Pagination tests
- Archive tests

---

## 16. Suggested Folder Structure (Phase 1)

```text
app/
├── models/
│   ├── notification.py
│   └── notification_preference.py
│
├── repositories/
│   ├── notification_repository.py
│   └── notification_preferences_repository.py
│
├── services/
│   ├── notification_service.py
│   ├── notification_preference_service.py
│   └── notification_template_service.py
│
├── schemas/
│   ├── notifications.py
│   └── notification_settings.py
│
├── api/v1/routes/
│   ├── notifications.py
│   └── notification_settings.py
│
├── api/v1/deps/
│   └── notifications.py
│
└── constants/
    ├── notification_types.py
    └── notification_messages.py
```

---

## 17. Sprint Breakdown (Phase 1)

### Sprint 1

- Database schema + migrations
- Notification models
- Repository layer
- Service layer
- Notification APIs

### Sprint 2

- Lead workflow integration
- Agent workflow integration
- Read/unread implementation
- Archive implementation
- Notification preferences APIs

### Sprint 3

- Admin announcement system (in-app)
- Polling optimization
- Performance tuning
- Future realtime preparation (no websocket in Phase 1)

---

## 18. Future Compatibility

Phase 1 architecture must support adding later (without major DB redesign):

- Email notifications
- SMS notifications
- Push notifications
- Queue/workers
- WebSocket realtime
- Delivery tracking + retry mechanisms

