# Backend API reference

Generated from the current FastAPI routes, Pydantic schemas, serializers, service validation, and authorization dependencies.

## 1. Conventions

- API base path: `/api/v1`
- JSON requests use `Content-Type: application/json`.
- Protected routes use `Authorization: Bearer <access_token>`.
- `Accept-Language` is optional. Supported configured locales default to `en`, `ar`, `fr`, and `es`.
- Access tokens must be JWTs with token type `access`; the referenced user must exist and be active.
- Roles used by the backend: `super_admin`, `admin`, `agent`, `owner`, and `registered_user`.
- Role aliases accepted by authentication: `agency` and `agency_admin` → `admin`; `property_owner` → `owner`; `user` → `registered_user`.
- In role dependencies, `admin`, `agency`, and `agency_admin` are treated as equivalent.
- There are no WebSocket or Server-Sent Events endpoints in the current application. Notifications are retrieved by HTTP polling.

### Success envelope

Most `/api/v1` handlers return:

```json
{
  "success": true,
  "message": "Optional message or null",
  "data": {},
  "error": null,
  "meta": {}
}
```

Some property/search routes declare Pydantic response models and return their model shape directly; those exceptions are documented with the endpoint.

### Error formats

The application has no global exception wrapper. Frontends must support both forms:

```json
{ "detail": "Human-readable error" }
```

```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable error",
    "details": {}
  }
}
```

FastAPI/Pydantic request validation returns HTTP `422`:

```json
{
  "detail": [
    {
      "loc": ["body", "field"],
      "msg": "Validation message",
      "type": "Validation error type"
    }
  ]
}
```

Status behavior used throughout the API:

- `400`: failed business validation or invalid transition
- `401`: missing/invalid token, inactive user, or invalid credentials
- `403`: authenticated but wrong role or outside the permitted agency/resource scope
- `404`: resource not found
- `409`: duplicate/conflicting resource or operation
- `422`: FastAPI/Pydantic path, query, form, or body validation
- `500`: uncaught server/storage error; upload endpoints can explicitly return upload errors

Endpoints list only their code-specific errors below. Any endpoint can return `422` for malformed typed input and `500` for an unhandled server/database failure.

### Pagination

The common page shape is:

```json
{
  "total": 42,
  "page": 1,
  "pageSize": 10,
  "totalPages": 5,
  "hasNext": true,
  "hasPrevious": false,
  "items": []
}
```

Unless an endpoint says otherwise, `page` is clamped to at least `1` and `pageSize` to `1..100`. Several endpoints duplicate pagination under `meta.pagination`.

## 2. Health

### `GET /health`

- Purpose: Docker/service health probe.
- Auth: none.
- Headers/params/body: none.
- Success `200` (not wrapped):

```json
{ "status": "healthy", "service": "realestate-api" }
```

## 3. Authentication

All paths in this section start with `/api/v1/auth`.

### `POST /api/v1/auth/login/password`

- Purpose: password sign-in and token issuance.
- Auth: public.
- Body: `username` (string, required), `password` (string, required), `rememberMe` (boolean, optional, default `false`; currently unused).
- Success `200`:

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "<jwt>",
    "refresh_token": "<jwt>",
    "id_token": "<jwt>",
    "token_type": "Bearer",
    "expires_in": 3600,
    "requires_password_set": false,
    "remember_me_cookie": false
  },
  "error": null,
  "meta": {}
}
```

- Errors: `401 Invalid credentials`; `403` when an agent profile is not `ACTIVE`; `422` invalid body.
- Integration: store the access and refresh tokens client-side. `rememberMe` does not alter backend behavior.

### `POST /api/v1/auth/login/otp/request`

- Purpose: create a passwordless-login OTP challenge.
- Auth: public.
- Body: `username` (string, required).
- Success data: `{ "session": "<challenge-uuid>" }`. The OTP is sent by email or SMS and is never included in the response.
- Errors: `401 Invalid account`; `403` agent not active; `422`.
- Integration: use `session` with `/auth/login/otp/verify`; the user enters the code from email or SMS.

### `POST /api/v1/auth/login/otp/verify`

- Purpose: verify login OTP and issue tokens.
- Auth: public.
- Body: `username`, `code`, `session` (all strings, required; `session` must parse as UUID).
- Success: same token data as password login.
- Errors: `400 Invalid OTP session`, verification code missing/expired/invalid; `401 Invalid account`; `403` agent not active; `422`.

### `POST /api/v1/auth/signup`

- Purpose: register a user and create signup OTP.
- Auth: public.
- Body: `full_name`, `email`, `password`, `role` (strings, required); `phone_number` (string/null, optional).
- Success data: `{}`. A verification OTP is emailed and is never included in the response.
- Errors: `409 User already exists`; `422`.
- Validation/constants: email is normalized lowercase; `role` uses the aliases in section 1.

### `POST /api/v1/auth/confirm-signup`

- Purpose: verify signup email.
- Auth: public.
- Body: `email`, `code` (strings, required).
- Success data: `{ "verified": true }`.
- Errors: `404 Account not found`; `400` OTP missing/expired/invalid; `422`.

### `POST /api/v1/auth/resend-confirmation`

- Purpose: resend signup email OTP.
- Auth: public.
- Body: `email` (string, required).
- Success data: `{}`. A verification OTP is emailed and is never included in the response.
- Errors: `404 Account not found`; `400 Account is already verified`; `422`.

### `GET /api/v1/auth/me`

- Purpose: current user profile.
- Auth: Bearer token.
- Success data: [User object](#user-object).
- Errors: `401 Authentication is required`; `404 User not found`.

### `PATCH /api/v1/auth/me`

- Purpose: directly update email and/or phone; changed fields become unverified.
- Auth: Bearer token.
- Body: `email` (string/null, optional), `phone_number` (string/null, optional).
- Success: User object; message `Profile updated successfully`.
- Errors: `401`, `404`, `422`.

### `PATCH /api/v1/auth/me/profile/request`

- Purpose: start OTP-verified email/phone update.
- Auth: Bearer token.
- Body: `email` and/or `phone_number` (optional strings/null).
- Success data:

```json
{
  "message": "Verification code sent.",
  "requires_verification": true,
  "verification_fields": ["email"]
}
```

OTP values are sent by email/SMS and are never included in the response.

- Errors: `401`, `404`, `422`.

### `POST /api/v1/auth/me/profile/verify`

- Purpose: finish OTP-verified profile update.
- Auth: Bearer token.
- Body: optional `email`, `email_otp`, `phone_number`, `phone_otp`; must contain either email+OTP or phone+OTP.
- Success data: `{ "message": "Profile updated successfully" }`.
- Errors: `400 Verification payload is incomplete` or OTP errors; `401`; `404`; `422`.

### `POST /api/v1/auth/me/profile-picture`

- Purpose: set a development profile-picture URL.
- Auth: Bearer token.
- Body: `file_name` and `content_type` (strings, required), `file_size` (integer, optional, `>=0`).
- Success data: `{ "upload_url": "dev://profile-pictures/{user_id}/{file_name}" }`.
- Errors: `401`, `404`, `422`.
- Integration: this endpoint does not receive file bytes.

### `DELETE /api/v1/auth/me/profile-picture`

- Purpose: remove current profile picture.
- Auth: Bearer token.
- Success: User object; message `Profile picture removed`.
- Errors: `401`, `404`.

### `POST /api/v1/auth/forgot-password/request`

- Purpose: request password-reset OTP without disclosing whether an account exists.
- Auth: public.
- Body: optional `email`, `phoneCountryCode`, `phoneNationalNumber`.
- Success: `data: true`; `meta` is empty. When the account exists, a verification OTP is sent by email and is never included in the response.
- Errors: `422`.

### `POST /api/v1/auth/forgot-password/confirm`

- Purpose: reset password using OTP.
- Auth: public.
- Body: `email`, `code`, `new_password` (strings, required).
- Success data: `{ "updated": true }`.
- Errors: `404 Account not found`; `400` OTP errors; `422`.

### `POST /api/v1/auth/change-password`

- Purpose: authenticated password change.
- Auth: Bearer token.
- Body: `password` (new password) and `previous_password` (strings, required).
- Success data: `{ "updated": true }`.
- Errors: `401 Authentication is required` or `Current password is invalid`; `422`.

### `POST /api/v1/auth/refresh`

- Purpose: replace token bundle using a refresh token.
- Auth: refresh token in body, not Authorization header.
- Body: `username` (required, must match token user's email), `refresh_token` (string/null; effectively required).
- Success: token bundle shown under password login.
- Errors: `401 Refresh token is required` or `Invalid refresh token`; `403` agent not active; `422`.

### `POST /api/v1/auth/logout`

- Purpose: acknowledge client logout.
- Auth: public.
- Body: none.
- Success data: `{ "logged_out": true }`.
- Integration: no server-side token revocation occurs; delete local tokens.

### User object

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "full_name": "Name",
  "phone_number": "+962...",
  "is_active": true,
  "is_email_verified": true,
  "is_phone_verified": false,
  "profile_picture_url": null,
  "roles": [
    {
      "id": "uuid",
      "name": "admin",
      "description": null,
      "permissions": [],
      "created_at": "ISO-8601|null"
    }
  ],
  "agency": null,
  "agencies": [],
  "has_agency": false,
  "created_at": "ISO-8601|null",
  "requires_password_set": false,
  "status": "active"
}
```

## 4. Users

All paths start with `/api/v1/users` and require a Bearer token.

### `PATCH /api/v1/users/agency`

- Purpose: link the current owner/user to an active verified agency.
- Body: `{ "agencyId": "<uuid-string>" }`.
- Success: User object; message `Agency assigned successfully`.
- Errors: `404 Agency not found`; `400 Owner is already linked to an agency`; `500` currently possible for a non-UUID string; `401`; `422`.
- Integration: multiple owner agencies are disabled by default (`ALLOW_OWNER_MULTIPLE_AGENCIES=false`).

### `GET /api/v1/users/recent-views`

- Purpose: paginated current-user property history.
- Query: `page=1`, `pageSize=10` (clamped `1..100`).
- Success data: common pagination plus `items`.
- Item: `id` UUID, `user_id` UUID, `property_hash_id` integer, `property_hash` integer, `property` [property listing object](#property-listing-object).
- Errors: `401`.

### `POST /api/v1/users/recent-views`

- Purpose: record/refresh a view, deduplicated by user+property.
- Body: `{ "property_hash_id": 123 }`.
- Success: one recent-view item.
- Errors: `404 Property not found`; `401`; `422`.

### `DELETE /api/v1/users/recent-views`

- Purpose: clear all current-user recent views.
- Success data: `true`.
- Errors: `401`.

### `DELETE /api/v1/users/recent-views/{property_hash_id}`

- Purpose: delete one current-user recent view.
- Path: `property_hash_id` integer.
- Success data: `true`.
- Errors: `404`; `401`; `422`.

## 5. Agency

Paths start with `/api/v1/agency`.

### Agency object

Agency responses contain: `id`, `agency_id` (same UUID), `agency_name`, `agency_trade_name`, `legal_document_s3_link`, `email`, `phone`, `logo_url`, `profile_picture_url` (same as logo), `website`, `address`, `city`, `state`, `country`, `zip_code`, `is_active`, `is_verified`, `status`, `agency_status` (`Active|Inactive`), `verification_status` (`Verified|Rejected|Pending Verification`), `currency` (default `JOD`), `measurement_unit` (default `sqm`), `created_at`, and `updated_at`.

### `POST /api/v1/agency/register`

- Purpose: public self-service agency registration.
- Auth: public.
- Headers: `Content-Type: multipart/form-data`.
- Form: `agency_name`, `agency_trade_name`, `email`, `phone_number`, `legal_document` (all required); `password` optional and currently unused.
- Success data: `{ "agency": <Agency> }`. A verification OTP is emailed and is never included in the response.
- Errors: `409` duplicate admin email; `422` invalid/missing form fields.
- Integration: creates a pending, inactive, unverified agency and an admin user. Upload bytes are accepted only here.

### `POST /api/v1/agency/offline-registration`

- Purpose: super-admin offline agency creation.
- Auth: `super_admin`.
- Body required: `agency_name`, `agency_trade_name`, `email`, `phone`.
- Optional body: `legal_document_s3_link`, `website`, `address`, `city`, `state`, `country`, `zip_code`, `currency` (default `JOD`), `measurement_unit` (default `sqm`).
- Success data: `{ "agency": <Agency>, "password_setup_token": null, "password_setup_link": null }`.
- Errors: `401`, `403`, `409`, `422`.

### `POST /api/v1/agency/invitations`

- Purpose: invite an agency.
- Auth: `super_admin`.
- Body: `email` required; optional `agency_name`, `agency_trade_name`, `phone`.
- Success data: invitation object with `id`, `email`, agency fields, `status`, relative `invitation_link`, `expires_at`, `accepted_at`, `revoked_at`, `created_at`, `updated_at`.
- Errors: `409 Agency already exists`; `401`; `403`; `422`.

### `GET /api/v1/agency/invitations/validate`

- Purpose: validate a public agency invitation.
- Auth: public.
- Query: `token` string, required.
- Success: invitation object.
- Errors: `404 Invitation not found`; `422`.

### `POST /api/v1/agency/invitations/accept`

- Purpose: accept invitation and submit an agency.
- Auth: public.
- Body required: `token`, `agency_name`, `agency_trade_name`, `phone`.
- Optional: `legal_document_s3_link`, `website`, `address`, `city`, `state`, `country`, `zip_code`.
- Success data: `{ "agency": <Agency>, "password_setup_token": null|string, "password_setup_link": null|string }`.
- Errors: `404 Invitation not found`; `400 Invitation is {status}`; `422`.

### `POST /api/v1/agency/invitations/{invitation_id}/revoke`

- Purpose: revoke a pending invitation.
- Auth: `super_admin`.
- Path: `invitation_id` UUID.
- Success: invitation object.
- Errors: `404`; `400 Only active invitations can be revoked`; `401`; `403`; `422`.

### `POST /api/v1/agency/password/setup`

- Purpose: set the approved agency admin password.
- Auth: public; challenge token in body.
- Body: `token`, `password` required.
- Success: agency response wrapper.
- Errors: `400` invalid/expired link or agency not approved; `404 Agency account not found`; `422`.

### `GET /api/v1/agency/list`

- Purpose: role-scoped agency list.
- Auth: Bearer token.
- Query: `skip=0`, `limit=20` (clamped `1..100`), optional `search`, `agencyStatus` (`active|inactive`), `verificationStatus` (`verified|rejected|pending verification|pending`), `sortBy=created_at` (`created_at|agency_name|email|status`), `sortOrder=desc` (`asc|desc`).
- Scope: super admin all; admin own agency; other roles active/verified selectable agencies.
- Success data: `[<Agency>]`; `meta.pagination = { "total": 0, "skip": 0, "limit": 20 }`.
- Errors: `401`, `422`.

### `GET /api/v1/agency/{agency_id}`

- Purpose: agency detail.
- Auth: `admin` scoped to own agency or `super_admin`.
- Path: `agency_id` UUID.
- Success: Agency object.
- Errors: `401`, `403`, `404`, `422`.

### `PUT /api/v1/agency/{agency_id}`

- Purpose: update agency profile.
- Auth: scoped `admin` or `super_admin`.
- Body: all optional: `agency_name`, `agency_trade_name`, `website`, `address`, `city`, `state`, `country`, `zip_code`, `currency`, `measurement_unit`.
- Success data: `{ "agency": <Agency>, "legal_document_upload": null }`.
- Errors: `401`, `403`, `404`, `422`.

### `POST /api/v1/agency/{agency_id}/review`

- Purpose: approve/reject registration.
- Auth: `super_admin`.
- Body: `action` required (`approve|reject`, case-insensitive), optional `reason`.
- Success: agency response wrapper; approval can return password setup token/link.
- Errors: `400 Invalid agency review action`; `401`; `403`; `404`; `422`.

### `POST /api/v1/agency/{agency_id}/activation`

- Purpose: activate/deactivate agency and linked users/submissions.
- Auth: `super_admin`.
- Body: `{ "is_active": true }`.
- Success: agency response wrapper.
- Errors: `400 Agency must be verified before activation`; `401`; `403`; `404`; `422`.

### `POST /api/v1/agency/{agency_id}/password-link`

- Purpose: regenerate approved-agency password setup link.
- Auth: `super_admin`.
- Success: agency response wrapper with token/link.
- Errors: `400 Agency must be approved before password link can be sent`; `401`; `403`; `404`.

### `POST /api/v1/agency/{agency_id}/logo`

- Purpose: generate development logo upload URL.
- Auth: scoped `admin` or `super_admin`.
- Body: `file_name`, `content_type`, `file_size` required.
- Success data: `{ "upload_url": "dev://agency-logos/{agency_id}/{file_name}" }`.
- Errors: `401`, `403`, `404`, `422`.

### `DELETE /api/v1/agency/{agency_id}/logo`

- Purpose: clear agency logo.
- Auth: scoped `admin` or `super_admin`.
- Success: Agency object.
- Errors: `401`, `403`, `404`.

### `POST /api/v1/agency/{agency_id}/legal-document`

- Purpose: generate development legal-document upload URL.
- Auth: scoped `admin` or `super_admin`.
- Body: `file_name`, `content_type`, `file_size` required.
- Success data: `{ "upload_url": "dev://agency-legal-documents/{agency_id}/{file_name}" }`.
- Errors: `401`, `403`, `404`, `422`.

### `GET /api/v1/agency/{agency_id}/owners`

- Purpose: agency-scoped owner list.
- Auth: scoped `admin` or `super_admin`.
- Query: `page=1`, `pageSize=10`; optional `search`, `status` (`all|active|enabled|suspended|inactive|disabled`).
- Success: common pagination with owner list items: `owner_id`, `full_name`, `email`, `phone`, `nationality:null`, `ssi:null`, `address:null`, `documents:[]`, timestamps, `status` (`ACTIVE|SUSPENDED`), `property_owned`.
- Errors: `401`, `403`, `404`, `422`.

### `GET /api/v1/agency/owners`

- Purpose: platform-wide owner list.
- Auth: `super_admin`.
- Query: same as previous plus optional `agencyId` UUID.
- Success: paginated owner items including `assigned_agencies`.
- Errors: `401`, `403`, `422`.

### `GET /api/v1/agency/owners/{owner_id}`

- Purpose: management owner detail.
- Auth: `admin` or `super_admin`, agency-scoped.
- Path: `owner_id` UUID.
- Success: [Owner object](#owner-object).
- Errors: `401`; `403` structured `FORBIDDEN`; `404`; `422`.

### `PATCH /api/v1/agency/owners/{owner_id}`

- Purpose: update owner identity fields.
- Auth: `admin` or `super_admin`, agency-scoped.
- Body: at least one of `full_name` (alias `fullName`), `email`, `phone_number` (aliases `phoneNumber`, `phone`).
- Validation: non-empty name/email; phone must be E.164 `^\+[1-9]\d{7,14}$`.
- Success: Owner object.
- Errors: `400 VALIDATION_ERROR`; `409 CONFLICT` email; `401`; `403`; `404`; `422`.

### `PATCH /api/v1/agency/owners/{owner_id}/status`

- Purpose: activate/deactivate owner.
- Auth: `admin` or `super_admin`, agency-scoped.
- Body: `status` required; optional `reason`.
- Status aliases: `ACTIVE|ENABLED`; `SUSPENDED|INACTIVE|DISABLED`.
- Success: Owner object.
- Errors: `400` invalid/already target status; `401`; `403`; `404`; `422`.

### `POST /api/v1/agency/owners/{owner_id}/agency`

- Purpose: assign owner to an agency.
- Auth: `super_admin`.
- Body: `{ "agency_id": "<uuid>" }`.
- Success data: mapping with `id`, `owner_id`, `agency_id`, `relationship_type:"property_owner"`, `status`, `is_primary`.
- Errors: `404` owner or active verified agency; `401`; `403`; `422`.

## 6. Leads

Paths start with `/api/v1/leads`.

Enums:

- `LeadSource`: `EMAIL_FORM`, `PHONE`, `WHATSAPP`, `MANUAL_ADMIN`, `AGENT_MANUAL`, `OFFLINE_MANUAL`
- `LeadStatus` request enum: `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`. `REQUEST_FOR_CLOSE` is a workflow command and is not persisted as the lead's status.
- `LeadMessageChannel`: `IN_APP`, `EMAIL`, `SMS`
- Close-request status: `PENDING`, `APPROVED`, `REJECTED`, `CANCELED`

### Lead object

`id`, `lead_number`, `property_id`, `property_hash`, embedded `property`, `user_id`, `inquiry_type`, `message`, `status`, `source`, `assigned_agent_id`, `assigned_by_admin_id`, `last_activity_at`, `request_close_at`, `closed_at`, `closed_by_admin_id`, `contact_name`, `contact_phone`, `contact_email`, `external_property_name`, `communication_mode`, `created_by_agent_id`, `created_by_admin_id`, `created_at`, `updated_at`.

### `POST /api/v1/leads`

- Purpose: public/authenticated property inquiry.
- Auth: optional Bearer; authenticated user ID is attached.
- Body: `property_hash` (integer|string, required); optional `inquiry_type` (default `general`, max 50), `message`, `source` (default `EMAIL_FORM`), `communication_mode` (default `IN_APP`), `contact_name` (max 255), `contact_email` (email), `contact_phone` (max 50).
- Success: Lead object; message `Lead created successfully`.
- Errors: `404 Property not found`; `422`.

### `GET /api/v1/leads`

- Purpose: role-scoped leads.
- Auth: Bearer token.
- Query: `page=1`, `pageSize=10`, optional exact `status`.
- Sorting: `updated_at DESC`, then `created_at DESC`.
- Success: common pagination plus `items:[<Lead>]`, duplicated under `meta.pagination`.
- Errors: `401`, `422`.

### `GET /api/v1/leads/my-enquiries`

- Purpose: Owner “My Enquiries” list, strictly scoped to `Lead.user_id == authenticated user ID`.
- Auth: `owner` or `registered_user`; Agent/Admin roles receive `403`.
- Query: `page=1`, `pageSize=10`, optional `search`, `status`, `source`, `inquiryType`, `assignedAgentId`; `sortBy=updated_at`, `sortOrder=desc`.
- Search fields: lead number, owner contact name/email/phone, property name, inquiry type, and message.
- Sort fields: `created_at|createdAt`, `updated_at|updatedAt`, `last_activity_at|lastActivityAt`, `lead_number|leadNumber`, `status`, `source`.
- Success: common pagination with both `items` and `enquiries` containing the same Owner-only Lead rows.
- Errors: `401`, `403`, `422`.

### `GET /api/v1/leads/{lead_id}`

- Purpose: lead detail.
- Auth: Bearer + lead access.
- Path: UUID.
- Success: Lead object.
- Errors: `401`, `403`, `404`, `422`.

### `PATCH /api/v1/leads/{lead_id}/assign`

- Purpose: assign/unassign agent.
- Auth: agency admin or super admin with lead access.
- Body: `{ "agent_id": "<uuid|null>" }`.
- Success: updated Lead; assigning a `NEW` lead moves it to `IN_PROGRESS`.
- Errors: `400 Agent not found` or deal-closed property read-only; `403` non-admin/outside agency/no access; `404`; `422`.

### `PATCH /api/v1/leads/{lead_id}/status`

- Purpose: status transition, or close-request creation when `status=REQUEST_FOR_CLOSE`.
- Auth: Bearer + lead access.
- Body: `status` required (`LeadStatus`), optional `reason`.
- Success for `REQUEST_FOR_CLOSE`: unchanged Lead fields plus `close_request` with status `PENDING`.
- Success for other allowed transitions: Lead object.
- Validation: direct `CLOSED` is rejected; a lead can close only through approval of a pending close request.
- Errors: `400` invalid/direct-close status, duplicate pending request, closed lead, or read-only property; `403` invalid request role; `404`; `422`.

### `POST /api/v1/leads/{lead_id}/request-close`

- Purpose: compatibility endpoint to create a separate pending close request without changing lead status.
- Auth: agent/admin/super admin with access.
- Body: optional `{ "reason": "string|null" }`.
- Success: unchanged Lead fields plus `close_request`.
- Errors: `400`, `401`, `403`, `404`.

### `GET /api/v1/leads/{lead_id}/close-requests`

- Purpose: list the lead's close requests, newest first.
- Auth: Bearer + lead access.
- Success data: `{ "items": [<CloseRequest>] }`.
- CloseRequest fields: `id`, `lead_id`, `requested_by`, `status`, `reason`, `reviewed_by`, `review_reason`, `requested_at`, `reviewed_at`, `canceled_by`, `canceled_at`, `created_at`, `updated_at`.
- Errors: `401`, `403`, `404`, `422`.

### `POST /api/v1/leads/close-requests/{request_id}/approve`

- Purpose: Agency Admin approval; this is the transition that changes the lead to `CLOSED`.
- Auth: agency `admin` with lead/agency access.
- Body: optional `{ "reason": "string|null" }`.
- Success data: `{ "lead": <Lead status=CLOSED>, "close_request": <CloseRequest status=APPROVED> }`.
- Errors: `400` already resolved; `401`; `403`; `404`; `422`.

### `POST /api/v1/leads/close-requests/{request_id}/reject`

- Purpose: Agency Admin rejection; lead status remains unchanged.
- Auth: agency `admin` with lead/agency access.
- Body: optional reason.
- Success data: unchanged `lead` plus close request status `REJECTED`.
- Errors: `400`, `401`, `403`, `404`, `422`.

### `POST /api/v1/leads/close-requests/{request_id}/cancel`

- Purpose: cancel a pending request; lead status remains unchanged.
- Auth: original requester or Agency Admin with lead access.
- Body: optional reason.
- Success data: unchanged `lead` plus close request status `CANCELED`.
- Errors: `400`, `401`, `403`, `404`, `422`.

### `POST /api/v1/leads/{lead_id}/close`

- Purpose: compatibility approval endpoint for the lead's existing pending close request.
- Auth: agency `admin` with access.
- Body: optional `{ "reason": "string|null" }`; body may be omitted.
- Success data: `{ "lead": <Lead status=CLOSED>, "close_request": <CloseRequest status=APPROVED> }`.
- Errors: `400 No pending close request exists` or already resolved; `401`; `403`; `404`; `422`.

### `GET /api/v1/leads/{lead_id}/notes`

- Purpose: internal notes, oldest first.
- Auth: Bearer + lead access. Only admin/super admin/assigned agent receives notes; other authorized users receive `items:[]`.
- Success data: `{ "items": [{ "id", "lead_id", "author_user_id", "note", "created_at", "updated_at" }] }`.
- Errors: `401`, `403`, `404`, `422`.

### `POST /api/v1/leads/{lead_id}/notes`

- Purpose: add internal note.
- Auth: Bearer + lead access.
- Body: `{ "note": "non-empty string" }`.
- Success: note object.
- Errors: `400` read-only property; `401`, `403`, `404`, `422`.

### `GET /api/v1/leads/{lead_id}/activity`

- Purpose: chronological status and assignment timeline.
- Auth: Bearer + lead access.
- Success data: `{ "items": [...] }`, oldest first.
- Status item: `id`, `kind:"status_change"`, `activity_type:"status_change"`, `message`, `user_id`, `from_status`, `to_status`, `reason`, `actor_role`, `created_at`.
- Audit item: `id`, `kind:"audit"`, `activity_type`, `message`, `user_id`, `tone`, `created_at`.
- Errors: `401`, `403`, `404`, `422`.

### `GET /api/v1/leads/{lead_id}/messages`

- Purpose: lead message thread, oldest first.
- Auth: Bearer + lead access.
- Success data: `{ "items": [{ "id", "lead_id", "sender_user_id", "recipient_user_id", "message", "channel", "delivery_state", "created_at" }] }`.
- Errors: `401`, `403`, `404`, `422`.

### `POST /api/v1/leads/{lead_id}/messages`

- Purpose: send/log message.
- Auth: Bearer + lead access.
- Body: `message` required/non-empty; `channel` default `IN_APP`; optional `recipient_user_id` UUID.
- Success: message object.
- Persistence: EMAIL stays `EMAIL`; SMS is stored as `IN_APP`; email/SMS use `delivery_state:"logged"`, in-app uses `"created"`.
- Errors: `400` read-only property; `401`, `403`, `404`, `422`.

## 7. Agents

Paths start with `/api/v1/agents`.

Agent statuses: `ACTIVE`, `INVITED`, `PENDING_PASSWORD`, `PENDING_REVIEW`, `DECLINED`, `INACTIVE`, `DELETED`.

Agent responses include `id`, `email`, `fullName`, `phone`, `whatsappNumber`, `serviceArea`, `serviceAreas`, `position`, `identityDocumentUrl`, `status`, `invitedAt`, `invitedBy`, `formSubmittedAt`, `passwordSetAt`, `approvedAt`, `approvedBy`, `reviewedAt`, `reviewedBy`, `statusReason`, and `declineReason`.

### `GET /api/v1/agents`

- Purpose: agent directory.
- Auth: any authenticated user. Only admin aliases/super admin can view rows; other roles receive an empty page.
- Query: `page=1`, `pageSize=10`, `sortBy=invited_at` (`invited_at|email|fullName|status|reviewedAt|formSubmittedAt`), `sortOrder=desc`, optional `search`, optional `status`.
- Status filters: `all`, `active`, `inactive`, `invited`, `pending`, `pending_review`, `pending_password`, `declined`, `deleted`; unknown values are uppercased.
- Success data: `{ "agents": [], "pagination": <common pagination> }`.
- Errors: `401`, `422`.

### `GET /api/v1/agents/summary`

- Purpose: agent dashboard totals and latest agents.
- Auth/visibility: same as list.
- Success data: `totalAgents`, `activeAgents`, `pendingInvites`, `pendingPassword`, `pendingReview`, `declined`, `lastFiveAgents`.
- Errors: `401`.

### `POST /api/v1/agents/invite`

- Purpose: invite agent by email or phone.
- Auth: `admin` or `super_admin`.
- Body: optional `email`, `phone_number` (aliases `phoneNumber|phone`, E.164), `full_name` (alias `fullName`), `service_area` (alias `serviceArea`); email or phone is required.
- Success: invitation data containing agent identity plus `inviteLink`, snake/camel invitation IDs, URL/token, and expiry.
- Errors: `400 VALIDATION_ERROR` no agency/identity; `409 DUPLICATE_EMAIL|DUPLICATE_PHONE`; `401`, `403`, `422`.

### `GET /api/v1/agents/invitations/validate`

### `GET /api/v1/agents/invite/validate`

- Purpose: two aliases for public invitation validation.
- Query: `token` required.
- Success data: `id`, `email`, `phone`, `fullName`, `serviceArea`, `serviceAreas`, `position`, `status`, `purpose`, `expiresAt`, `alreadySubmitted`.
- Errors: `404 INVITATION_INVALID`; `400 INVITATION_INVALID|INVITATION_EXPIRED`; `422`.

### `POST /api/v1/agents/invitations/accept`

- Purpose: legacy password-only invitation acceptance.
- Auth: public.
- Body: `token`; `password` length `8..128`.
- Success: Agent object in `PENDING_REVIEW`.
- Errors: `400` invalid/expired/wrong-purpose invitation; `404`; `422`.

### `POST /api/v1/agents/invitations/submit`

### `POST /api/v1/agents/onboarding`

- Purpose: two aliases for onboarding form submission.
- Auth: public.
- Query: optional `token`, used only when body token absent.
- Body fields: optional `token`; `full_name` (minimum 2), `phone` (E.164), optional `whatsapp_number`, `service_area_ids`, `service_area`, `position`, `identity_document_url`, `email`.
- Validation: token required from body/query; at least one valid service area; body email is ignored and invitation email is authoritative.
- Success data: agent onboarding fields plus relative `passwordSetupLink`.
- Errors: `400 VALIDATION_ERROR` token/service area; `409` already submitted or duplicate identity; `404` invitation; `422`.

### `POST /api/v1/agents/password/setup`

- Purpose: set password from onboarding challenge.
- Auth: public.
- Body: `token`, `password` (`8..128`) required.
- Success: Agent object, status `PENDING_REVIEW`.
- Errors: `400` invalid/expired link; `404`; `422`.

### `POST /api/v1/agents/invitations/document-upload`

- Purpose: presigned identity-document upload before authentication.
- Auth: valid invitation token in body.
- Body: `token`, `file_name` (`.pdf|.jpg|.jpeg|.png`), non-empty `content_type`, `file_size` `1..5,242,880`.
- Success: upload object containing `upload_url`, `object_key`, `file_url`, `readable_url`, `signed_read_url`, `mode` (`s3|log`), `content_type`, `file_size`, and expiry fields.
- Errors: `400` invitation; `404`; `422`; `500 UPLOAD_ERROR`.

### `POST /api/v1/agents/manual-onboard`

- Purpose: admin-created onboarding.
- Auth: `admin` or `super_admin`.
- Body: `full_name`, email, E.164 phone, service area IDs/text, and optional WhatsApp, position, identity URL; same identity/service-area validation as onboarding.
- Success: Agent object plus `temporaryPassword`, `temporary_password`, `inviteLink`, `passwordSetupLink`.
- Errors: `400`, `409`, `401`, `403`, `422`.

### `POST /api/v1/agents/{agent_id}/resend-invitation`

- Purpose: resend onboarding or password-setup link.
- Auth: `admin` or `super_admin`.
- Path: agent UUID.
- Success: invitation/password link object.
- Errors: `400` caller has no agency; `403` outside agency; `404`; `401`; `422`.

### `DELETE /api/v1/agents/{agent_id}`

- Purpose: soft-delete agent, deactivate user, revoke invitations.
- Auth: `admin` or `super_admin`.
- Success data: `true`.
- Errors: `400`, `401`, `403`, `404`, `422`.

### `PATCH /api/v1/agents/{agent_id}/status`

- Purpose: approve, decline, or deactivate agent.
- Auth: `admin` or `super_admin`.
- Body: `status` (one of agent statuses), optional `reason`.
- Success: Agent object and status-specific message.
- Errors: `400 Invalid agent status`; `403` outside agency; `404`; `401`; `422`.
- Integration: onboarding does not activate login. Set status `ACTIVE` explicitly.

## 8. Owners

All `/api/v1/owners` routes require `admin` or `super_admin`.

### Owner object

The serializer returns compatibility duplicates: `id`, `owner_id`, `ownerId`, `full_name`, `fullName`, `email`, `phone`, `phone_number`, `phoneNumber`, `status`, `is_active`, `linked_properties_count`, `linkedPropertiesCount`, `linked_leads_count`, `linkedLeadsCount`, `property_owned`, `assigned_agencies`, `assignedAgencies`, timestamps, and placeholder `nationality`, `ssi`, `address`, `documents`.

### `GET /api/v1/owners`

- Purpose: paginated owner management list.
- Query: `page=1`, `pageSize=10`, `sortBy=created_at` (`created_at|createdAt|updated_at|updatedAt|email|full_name|fullName|phone|phoneNumber|status`), `sortOrder=desc`, optional `search`, optional status (`all|active|enabled|suspended|inactive|disabled`).
- Success data: `owners` and `items` (same rows), common pagination fields, and nested `pagination`.
- Errors: `401`, `403`, `422`.

### `GET /api/v1/owners/{owner_id}`

- Purpose: owner detail.
- Path: UUID.
- Success: Owner object.
- Errors: `400 Selected user is not a property owner`; `403 FORBIDDEN`; `404`; `401`; `422`.

### `PATCH /api/v1/owners/{owner_id}`

- Purpose: update owner.
- Body: at least one of `full_name|fullName`, `email`, `phone_number|phoneNumber|phone`; E.164 phone.
- Success: Owner object.
- Errors: `400 VALIDATION_ERROR`; `409 CONFLICT`; `401`, `403`, `404`, `422`.

### `PATCH /api/v1/owners/{owner_id}/status`

- Purpose: activate/deactivate via label.
- Body: `status`, optional `reason`; aliases are the same as agency owner-status endpoint.
- Success: Owner object.
- Errors: `400`, `401`, `403`, `404`, `422`.

### `PATCH /api/v1/owners/{owner_id}/activate`

- Purpose: activate owner and restore hidden properties.
- Body: none.
- Success: Owner object, potentially `restored_properties_count`.
- Errors: `400` already active; `401`, `403`, `404`.

### `PATCH /api/v1/owners/{owner_id}/deactivate`

- Purpose: deactivate and hide active listings.
- Body: optional `{ "confirm": true, "reason": null }`; default confirmation true.
- Success: Owner object, potentially `hidden_properties_count`.
- Errors: `400` confirmation false/already inactive; `401`, `403`, `404`, `422`.

### `GET /api/v1/owners/{owner_id}/properties`

- Purpose: owner submissions.
- Query: `page=1`, `pageSize=10`.
- Success: common pagination with both `items` and `properties`, containing submission objects.
- Errors: `401`, `403`, `404`, `422`.

### `GET /api/v1/owners/{owner_id}/leads`

- Purpose: leads on owner properties.
- Query: `page=1`, `pageSize=10`, optional exact `status`.
- Success: common pagination with both `items` and `leads`.
- Errors: `401`, `403`, `404`, `422`.

## 9. Deal closures

Paths start with `/api/v1/deal-closures`; all require Bearer authentication.

Closure statuses: `PENDING`, `APPROVED`, `REJECTED`. Review actions: `approve`, `reject`.

Closure object: `id`, `property_id`, `property_hash`, embedded `property`, `lead_id`, `agency_id`, `requested_by`, `status`, `reason`, `review_reason`, `reviewed_by`, `requested_at`, `reviewed_at`, `created_at`, `updated_at`.

### `POST /api/v1/deal-closures`

- Purpose: request property deal closure.
- Body: `property_hash` (integer|string), optional `lead_id` UUID, optional `reason`.
- Allowed: assigned/submitting agent or matching agency admin.
- Success: Closure object.
- Errors: `400` pending/approved closure already exists; `403`; `404` property; `401`; `422`.

### `GET /api/v1/deal-closures`

- Purpose: role-scoped closure list.
- Query: `page=1`, `pageSize=10`, optional `status` (uppercased).
- Scope: super admin all; admin agency; others own requests.
- Success: common pagination with `items`.
- Errors: `401`, `422`.

### `GET /api/v1/deal-closures/{closure_id}`

- Purpose: closure detail.
- Path: UUID.
- Success: Closure object.
- Errors: `401`, `403`, `404`, `422`.

### `POST /api/v1/deal-closures/{closure_id}/review`

- Purpose: approve/reject pending closure.
- Auth: agency `admin` only; current service review check does not grant super-admin bypass.
- Body: `action` (`approve|reject`), optional `reason`.
- Success: Closure object.
- Side effects: approve marks property deal-closed and optional linked lead `CLOSED`; reject restores property to active.
- Errors: `400` already reviewed/invalid action; `401`, `403`, `404`, `422`.

## 10. Favorites

All `/api/v1/favorites` routes require Bearer authentication.

### `GET /api/v1/favorites`

- Purpose: current-user favorites with embedded public listings.
- Query: `page=1`, `pageSize=10`.
- Sorting: favorite `created_at DESC`.
- Success: common pagination with items `{ "id", "user_id", "property_hash", "property": <Property listing> }`.
- Errors: `401`, `422`.
- Note: missing/non-public properties are skipped from `items` although their favorite rows remain in `total`.

### `POST /api/v1/favorites`

- Purpose: idempotently add favorite.
- Body: `{ "property_hash": 123 }` (integer required).
- Success: one favorite item; message `Favorite added successfully`.
- Errors: `401`; `404 Property not found`; `422`.

### `DELETE /api/v1/favorites/{property_hash}`

- Purpose: remove favorite.
- Path: flexible string matching property hash/UUID or favorite UUID.
- Success data: `true`.
- Errors: `400 Favorite not found`; `401`; possible `404 Property not found`.

## 11. Saved searches

All `/api/v1/saved-searches` routes require Bearer authentication and are scoped to the current user.

Saved-search object: `id`, `name`, free-form `search_criteria`, generated URL-encoded `query_string`, `notification_enabled`, `last_run_at`.

### `POST /api/v1/saved-searches`

- Purpose: save property filter criteria.
- Body: `name` length `1..255`; `search_criteria` object default `{}`; `notification_enabled` boolean default `false`.
- Success: Saved-search object.
- Errors: `401`, `422`.
- Integration: criteria are stored without field-level validation; notification matching is not implemented.

### `GET /api/v1/saved-searches`

- Purpose: list searches.
- Query: `page=1`, `pageSize=10`.
- Sorting: `updated_at DESC`.
- Success: common pagination with saved-search items.
- Errors: `401`, `422`.

### `GET /api/v1/saved-searches/{search_id}`

- Purpose: search detail.
- Path: UUID.
- Success: Saved-search object.
- Errors: `401`, `404`, `422`.

### `PATCH /api/v1/saved-searches/{search_id}`

- Purpose: update name/criteria.
- Body: optional `name` (`1..255`) and `search_criteria` object default `{}`.
- Success: Saved-search object.
- Errors: `401`, `404`, `422`.
- Note: `notification_enabled` cannot be updated by this schema.

### `DELETE /api/v1/saved-searches/{search_id}`

- Purpose: delete owned search.
- Success data: `true`.
- Errors: `401`, `404`, `422`.

## 12. Notifications

All `/api/v1/notifications` routes require Bearer authentication and are recipient-scoped.

Notification object: `id`, `typeKey`, `eventType`, `title`, `message`, `actionUrl`, `isRead`, `createdAt`, `readAt`, `archivedAt`, free-form `data`.

Known type keys: `lead_created`, `lead_assigned`, `lead_message`, `owner_deactivated`, `owner_activated`, `property_submission_created`, `property_submission_assigned_for_update`, dynamic `property_submission_{status}`, `property_deactivated`, dynamic `deal_closure_{status}`.

### `GET /api/v1/notifications`

- Purpose: recipient notifications.
- Query: `page=1`, `pageSize=10`, `includeArchived=false`.
- Sorting: `created_at DESC`.
- Success: common pagination with notification items.
- Errors: `401`, `422`.

### `GET /api/v1/notifications/unread-count`

- Purpose: non-archived unread count.
- Success data: `{ "unreadCount": 3 }`.
- Errors: `401`.

### `PUT /api/v1/notifications/read-all`

- Purpose: mark all non-archived notifications read.
- Success data: `{ "updated": 3 }`.
- Errors: `401`.

### `GET /api/v1/notifications/preferences`

- Purpose: read notification preference rows.
- Success data: `{ "items": [{ "id", "notification_type", "enabled", "created_at", "updated_at" }] }`, sorted by type.
- Errors: `401`.
- Integration: there is no preference mutation endpoint.

### `PUT /api/v1/notifications/{notification_id}/read`

- Purpose: mark one notification read.
- Path: UUID.
- Success: Notification object.
- Errors: `401`, `404`, `422`.

### `POST /api/v1/notifications/{notification_id}/archive`

- Purpose: archive one notification.
- Success data: `true`.
- Errors: `401`, `404`, `422`.

### `POST /api/v1/notifications/{notification_id}/unarchive`

- Purpose: unarchive one notification.
- Success data: `true`.
- Errors: `401`, `404`, `422`.

### `DELETE /api/v1/notifications/{notification_id}`

- Purpose: permanently delete one notification.
- Success data: `{ "id": "<notification-uuid>" }`.
- Errors: `401`, `404`, `422`.

Polling interval defaults to 30 seconds (`NOTIFICATION_POLL_INTERVAL_SECONDS`). Email and SMS modes default to `log`.

## 13. Audit logs

### `GET /api/v1/audit-logs`

- Purpose: activity/audit list.
- Auth: `admin` or `super_admin`.
- Query: `page=1`, `pageSize=25`, optional exact `activityType`.
- Scope: super admin all; admin current agency; admin without agency gets empty list.
- Sorting: `created_at DESC`.
- Success: common pagination with `{ "id", "user_id", "property_id", "activity_type", "message", "tone", "created_at", "updated_at" }`.
- Errors: `401`, `403`, `422`.
- Known types include lead create/assign/status, owner update/activation/deactivation/mapping, deal-closure request/review, agency invitation/review/activation, and property submission/revision/deactivation events.

## 14. Uploads and media URLs

All `/api/v1/uploads` routes require Bearer authentication.

Upload context enum:

- `owner_document`
- `property_media_image`
- `property_document`
- `agency_legal_document`
- `agent_identity_document`

S3 settings: `AWS_S3_BUCKET`; `AWS_REGION` default `us-west-2`; readable GET URL expiry default 3600 seconds; upload PUT URL expiry default 900 seconds.

### `POST /api/v1/uploads/presigned-url`

- Purpose: direct client upload URL.
- Body: `file_name` non-empty, `content_type` non-empty, `file_size >= 0`, `context` enum, optional `draft_client_id`, optional `submission_id`.
- Rules: owner documents require `draft_client_id`; property media/documents require `submission_id` or `draft_client_id`; agent identity documents allow `.pdf|.jpg|.jpeg|.png` and max 5 MiB.
- Object key: `{context}/{draft_client_id|submission_id|user_id}/{uuid}-{basename}`.
- S3 success data: `upload_url`, `object_key`, canonical `file_url`, `readable_url`, `signed_read_url`; meta: `mode:"s3"`, content type/size, expiry values.
- Dev success: all URLs use `dev://uploads/{object_key}`; meta `mode:"log"`.
- Errors: `400` context/content validation; `401`; `422`; `500 Could not generate upload URL`.
- Integration: PUT raw bytes to `upload_url` with the requested Content-Type, persist canonical `file_url`, and use signed read URL only for display.

### `POST /api/v1/uploads/readable-url`

- Purpose: turn stored URL into a fresh readable URL.
- Body: `{ "file_url": "non-empty string" }`.
- Success data: canonical `file_url`, `readable_url`, `signed_read_url`; meta contains read expiry.
- Errors: `400 file_url is required|Could not resolve media URL`; `401`; `422`.

Media responses canonicalize S3 URLs by stripping `X-Amz-*` query parameters. Read serializers presign recognized URL fields such as file/document/identity/logo/legal-document URLs.




