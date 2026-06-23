# Live Database Schema Inventory

Database: `abdoun_internal_db_shared`
Current schema: `public`

Alembic versions:

- `0053_owner_soft_delete`

PostgreSQL extensions:

- `plpgsql`

Enum types:

- `lead_message_channel_enum`: `IN_APP`, `EMAIL`
- `lead_source_enum`: `EMAIL_FORM`, `PHONE`, `WHATSAPP`, `MANUAL_ADMIN`, `AGENT_MANUAL`, `OFFLINE_MANUAL`
- `lead_status_enum`: `NEW`, `IN_PROGRESS`, `REQUEST_FOR_CLOSE`, `CLOSED`
- `property_view_user_type`: `guest`, `registered`

## Schema `public`

### `public.activity_logs`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | yes |  |  |
| property_id | UUID | yes |  |  |
| activity_type | VARCHAR(50) | yes |  |  |
| message | TEXT | yes |  |  |
| tone | VARCHAR(20) | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Indexes:

- `ix_activity_logs_created_at` on `created_at`
- `ix_activity_logs_user_id` on `user_id`

### `public.lead_messages`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| lead_id | UUID | no |  |  |
| sender_user_id | UUID | yes |  |  |
| recipient_user_id | UUID | yes |  |  |
| message | TEXT | no |  |  |
| channel | VARCHAR(6) | no | 'IN_APP'::lead_message_channel_enum |  |
| delivery_state | VARCHAR(32) | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `lead_id` -> `public.leads(id)`
- `recipient_user_id` -> `public.users(id)`
- `sender_user_id` -> `public.users(id)`

Indexes:

- `ix_lead_messages_created_at` on `created_at`
- `ix_lead_messages_lead_id` on `lead_id`

### `public.cities`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".cities_id_seq'::regclass) |  |
| name | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Indexes:

- `ix_cities_id` on `id`

### `public.alembic_version`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| version_num | VARCHAR(32) | no |  |  |

### `public.dashboard_summary`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | yes |  |  |
| total_properties | INTEGER | yes |  |  |
| active_properties | INTEGER | yes |  |  |
| draft_properties | INTEGER | yes |  |  |
| total_views | INTEGER | yes |  |  |
| total_inquiries | INTEGER | yes |  |  |
| total_deals | INTEGER | yes |  |  |
| conversion_rate | NUMERIC | yes |  |  |
| last_updated | TIMESTAMP | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Indexes:

- `ix_dashboard_summary_last_updated` on `last_updated`
- `ix_dashboard_summary_user_id` on `user_id`

### `public.lead_notes`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| lead_id | UUID | no |  |  |
| author_user_id | UUID | yes |  |  |
| note | TEXT | no |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `author_user_id` -> `public.users(id)`
- `lead_id` -> `public.leads(id)`

Indexes:

- `ix_lead_notes_created_at` on `created_at`
- `ix_lead_notes_lead_created` on `lead_id, created_at`
- `ix_lead_notes_lead_id` on `lead_id`

### `public.lead_status_history`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| lead_id | UUID | no |  |  |
| from_status | VARCHAR(17) | yes |  |  |
| to_status | VARCHAR(17) | no |  |  |
| actor_user_id | UUID | yes |  |  |
| actor_role | VARCHAR(32) | yes |  |  |
| reason | TEXT | yes |  |  |
| changed_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `actor_user_id` -> `public.users(id)`
- `lead_id` -> `public.leads(id)`

Indexes:

- `ix_lead_status_history_changed_at` on `changed_at`
- `ix_lead_status_history_lead_changed` on `lead_id, changed_at`
- `ix_lead_status_history_lead_id` on `lead_id`

### `public.lead_number_counters`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| year | INTEGER | no | nextval('"public".lead_number_counters_year_seq'::regclass) |  |
| last_value | INTEGER | no | 0 |  |

### `public.notification_preferences`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | no |  |  |
| notification_type | VARCHAR(100) | no |  |  |
| enabled | BOOLEAN | no | true |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `ix_notification_preferences_user_id` on `user_id`
- `uq_notification_preferences_user_type` on `user_id, notification_type` unique

### `public.admin_agent_assignments`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| admin_id | UUID | no |  |  |
| agent_id | UUID | no |  |  |
| is_active | BOOLEAN | no | true |  |
| assigned_at | TIMESTAMP | no | now() |  |
| revoked_at | TIMESTAMP | yes |  |  |
| can_inherit_privileges | BOOLEAN | no | false |  |

Foreign keys:

- `admin_id` -> `public.users(id)`
- `agent_id` -> `public.users(id)`

### `public.agent_invites`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| email | VARCHAR(255) | no |  |  |
| invited_by | UUID | no |  |  |
| token | VARCHAR(100) | no |  |  |
| expires_at | TIMESTAMP | no |  |  |
| is_used | BOOLEAN | no | false |  |
| created_at | TIMESTAMP | no | now() |  |
| invited_at | TIMESTAMP | yes | now() |  |
| revoked_at | TIMESTAMP | yes |  |  |
| revoked_by | UUID | yes |  |  |

Foreign keys:

- `invited_by` -> `public.users(id)`
- `revoked_by` -> `public.users(id)`

Indexes:

- `ix_agent_invites_email` on `email`
- `ix_agent_invites_token` on `token` unique

### `public.agent_profiles`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| user_id | UUID | no |  |  |
| service_area | VARCHAR(255) | yes |  |  |
| approved_by | UUID | yes |  |  |
| approved_at | TIMESTAMP | yes |  |  |
| status | VARCHAR(20) | no | 'INVITED'::character varying |  |
| reviewed_by | UUID | yes |  |  |
| reviewed_at | TIMESTAMP | yes |  |  |
| form_submitted_at | TIMESTAMP | yes |  |  |
| password_set_at | TIMESTAMP | yes |  |  |
| decline_reason | TEXT | yes |  |  |
| deleted_at | TIMESTAMP | yes |  |  |
| deleted_by | UUID | yes |  |  |
| status_reason | TEXT | yes |  |  |

Foreign keys:

- `approved_by` -> `public.users(id)`
- `user_id` -> `public.users(id)`
- `deleted_by` -> `public.users(id)`
- `reviewed_by` -> `public.users(id)`

Indexes:

- `ix_agent_profiles_deleted_at` on `deleted_at`
- `ix_agent_profiles_status` on `status`

### `public.category_features`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".category_features_id_seq'::regclass) |  |
| category_id | INTEGER | no |  |  |
| feature_id | INTEGER | no |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `category_id` -> `public.property_categories(id)`
- `feature_id` -> `public.features(id)`

Indexes:

- `ix_category_features_id` on `id`

### `public.features`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".features_id_seq'::regclass) |  |
| name | VARCHAR(100) | no |  |  |
| slug | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |
| category_id | INTEGER | yes |  |  |
| property_type_id | INTEGER | yes |  |  |
| feature_group | VARCHAR(50) | no | 'FEATURE'::character varying |  |
| display_order | INTEGER | no | 0 |  |

Foreign keys:

- `category_id` -> `public.property_categories(id)`
- `property_type_id` -> `public.property_types(id)`

Indexes:

- `features_slug_key` on `slug` unique
- `ix_features_category_id` on `category_id`
- `ix_features_feature_group` on `feature_group`
- `ix_features_id` on `id`
- `ix_features_property_type_id` on `property_type_id`
- `uq_features_amenity_name_per_category` on `category_id, name` unique
- `uq_features_feature_name_per_category_type` on `category_id, property_type_id, name` unique

### `public.category_search_fields`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".category_search_fields_id_seq'::regclass) |  |
| category_id | INTEGER | no |  |  |
| field_id | INTEGER | no |  |  |
| is_required | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `category_id` -> `public.property_categories(id)`
- `field_id` -> `public.search_fields(id)`

Indexes:

- `ix_category_search_fields_id` on `id`

### `public.leads`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| property_id | UUID | yes |  |  |
| user_id | UUID | yes |  |  |
| inquiry_type | VARCHAR(50) | yes |  |  |
| message | TEXT | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |
| status | VARCHAR(17) | no | 'NEW'::lead_status_enum |  |
| source | VARCHAR(14) | no | 'EMAIL_FORM'::lead_source_enum |  |
| assigned_agent_id | UUID | yes |  |  |
| assigned_by_admin_id | UUID | yes |  |  |
| last_activity_at | TIMESTAMP | yes |  |  |
| request_close_at | TIMESTAMP | yes |  |  |
| closed_at | TIMESTAMP | yes |  |  |
| closed_by_admin_id | UUID | yes |  |  |
| lead_number | VARCHAR(32) | no |  |  |
| external_owner_name | VARCHAR(255) | yes |  |  |
| external_owner_phone | VARCHAR(50) | yes |  |  |
| external_owner_email | VARCHAR(255) | yes |  |  |
| external_property_name | VARCHAR(255) | yes |  |  |
| communication_mode | VARCHAR(32) | no | 'IN_APP'::character varying |  |
| created_by_agent_id | UUID | yes |  |  |
| offline_inquiry_type | VARCHAR(64) | yes |  |  |
| offline_source | VARCHAR(64) | yes |  |  |
| offline_notes | TEXT | yes |  |  |
| created_by_admin_id | UUID | yes |  |  |

Foreign keys:

- `assigned_agent_id` -> `public.users(id)`
- `assigned_by_admin_id` -> `public.users(id)`
- `closed_by_admin_id` -> `public.users(id)`
- `created_by_admin_id` -> `public.users(id)`
- `created_by_agent_id` -> `public.users(id)`

Indexes:

- `ix_leads_agent_status_created` on `assigned_agent_id, status, created_at`
- `ix_leads_assigned_agent_id` on `assigned_agent_id`
- `ix_leads_created_at` on `created_at`
- `ix_leads_created_by_admin_id` on `created_by_admin_id`
- `ix_leads_created_by_agent_id` on `created_by_agent_id`
- `ix_leads_lead_number` on `lead_number` unique
- `ix_leads_property_id` on `property_id`
- `ix_leads_source` on `source`
- `ix_leads_source_created` on `source, created_at`
- `ix_leads_status` on `status`

### `public.agency_master`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| agency_name | VARCHAR(255) | no |  |  |
| agency_trade_name | VARCHAR(255) | no |  |  |
| legal_document_s3_link | TEXT | no |  |  |
| email | VARCHAR(255) | no |  |  |
| phone | VARCHAR(20) | no |  |  |
| website | VARCHAR(255) | yes |  |  |
| address | TEXT | yes |  |  |
| city | VARCHAR(100) | yes |  |  |
| state | VARCHAR(100) | yes |  |  |
| country | VARCHAR(100) | yes |  |  |
| zip_code | VARCHAR(20) | yes |  |  |
| is_active | BOOLEAN | no | true |  |
| is_verified | BOOLEAN | no | false |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |
| logo_url | TEXT | yes |  |  |
| currency | VARCHAR(3) | no | 'JOD'::character varying |  |
| measurement_unit | VARCHAR(20) | no | 'sqm'::character varying |  |

Indexes:

- `ix_agency_master_email` on `email`
- `ix_agency_master_phone` on `phone`
- `uq_agency_master_email` on `email` unique
- `uq_agency_master_phone` on `phone` unique

### `public.property_listing_submissions`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no | gen_random_uuid() |  |
| submitted_by | UUID | no |  |  |
| property_id | UUID | yes |  |  |
| status | VARCHAR(30) | no | 'draft'::character varying |  |
| current_step | INTEGER | no | 1 |  |
| last_completed_step | INTEGER | no | 0 |  |
| payload | JSONB | no | '{}'::jsonb |  |
| step_completion | JSONB | no | '{}'::jsonb |  |
| terms_accepted | BOOLEAN | no | false |  |
| privacy_accepted | BOOLEAN | no | false |  |
| public_display_authorized | BOOLEAN | no | false |  |
| fees_acknowledged | BOOLEAN | no | false |  |
| submitted_at | TIMESTAMP | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |
| reviewed_by | UUID | yes |  |  |
| reviewed_at | TIMESTAMP | yes |  |  |
| review_reason | TEXT | yes |  |  |
| deleted_at | TIMESTAMP | yes |  |  |
| deleted_by | UUID | yes |  |  |
| delete_reason | TEXT | yes |  |  |

Foreign keys:

- `deleted_by` -> `public.users(id)`
- `reviewed_by` -> `public.users(id)`
- `submitted_by` -> `public.users(id)`

Indexes:

- `ix_property_listing_submissions_deleted_at` on `deleted_at`
- `ix_property_listing_submissions_deleted_by` on `deleted_by`
- `ix_property_listing_submissions_property_id` on `property_id`
- `ix_property_listing_submissions_reviewed_by` on `reviewed_by`
- `ix_property_listing_submissions_status` on `status`
- `ix_property_listing_submissions_submitted_by` on `submitted_by`

### `public.property_features`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| property_id | UUID | no |  |  |
| feature_id | INTEGER | no |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |
| value | VARCHAR(255) | yes |  |  |

Foreign keys:

- `feature_id` -> `public.features(id)`

### `public.property_categories`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".property_categories_id_seq'::regclass) |  |
| name | VARCHAR(100) | no |  |  |
| slug | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Indexes:

- `ix_property_categories_id` on `id`
- `property_categories_slug_key` on `slug` unique

### `public.notifications`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| recipient_user_id | UUID | no |  |  |
| actor_user_id | UUID | yes |  |  |
| type_key | VARCHAR(100) | no |  |  |
| title | VARCHAR(255) | no |  |  |
| message | TEXT | no |  |  |
| data | JSONB | yes |  |  |
| is_read | BOOLEAN | no | false |  |
| created_at | TIMESTAMP | no | now() |  |
| read_at | TIMESTAMP | yes |  |  |
| archived_at | TIMESTAMP | yes |  |  |
| idempotency_key | VARCHAR(255) | yes |  |  |
| event_type | VARCHAR(100) | yes |  |  |
| action_url | TEXT | yes |  |  |

Foreign keys:

- `actor_user_id` -> `public.users(id)`
- `recipient_user_id` -> `public.users(id)`

Indexes:

- `idx_notifications_created` on `created_at`
- `idx_notifications_recipient` on `recipient_user_id`
- `idx_notifications_unread` on `recipient_user_id, is_read`
- `ix_notifications_actor_user_id` on `actor_user_id`
- `ix_notifications_archived_at` on `archived_at`
- `ix_notifications_event_type` on `event_type`
- `ix_notifications_is_read` on `is_read`
- `ix_notifications_recipient_user_id` on `recipient_user_id`
- `ix_notifications_type_key` on `type_key`
- `uq_notifications_idempotency` on `idempotency_key` unique

### `public.owner`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| owner_id | UUID | no |  |  |
| full_name | VARCHAR(100) | yes |  |  |
| email | VARCHAR(150) | yes |  |  |
| phone | VARCHAR(20) | yes |  |  |
| nationality | VARCHAR(100) | yes |  |  |
| ssi | VARCHAR(50) | yes |  |  |
| address | TEXT | yes |  |  |
| documents | JSONB | no | '[]'::jsonb |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |
| user_id | UUID | yes |  |  |
| deleted_at | TIMESTAMP | yes |  |  |
| deleted_by | UUID | yes |  |  |

Foreign keys:

- `deleted_by` -> `public.users(id)`
- `user_id` -> `public.users(id)`

Indexes:

- `ix_owner_deleted_at` on `deleted_at`
- `ix_owner_deleted_by` on `deleted_by`
- `ix_owner_email` on `email`
- `ix_owner_phone` on `phone`
- `ix_owner_user_id` on `user_id`

### `public.permissions`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| code | VARCHAR(100) | no |  |  |
| description | TEXT | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |

Indexes:

- `ix_permissions_code` on `code` unique

### `public.property_media`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".property_media_id_seq'::regclass) |  |
| property_id | UUID | no |  |  |
| media_type | VARCHAR(20) | no |  |  |
| url | TEXT | no |  |  |
| thumb_url | TEXT | yes |  |  |
| is_primary | BOOLEAN | yes | false |  |
| display_order | INTEGER | yes | 0 |  |
| caption | TEXT | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Indexes:

- `idx_property_media_property_id` on `property_id`
- `idx_property_media_property_type_order` on `property_id, media_type, display_order`

### `public.property_status`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".property_status_id_seq'::regclass) |  |
| name | VARCHAR(50) | no |  |  |
| slug | VARCHAR(50) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Indexes:

- `ix_property_status_id` on `id`
- `property_status_slug_key` on `slug` unique

### `public.property_translations`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".property_translations_id_seq'::regclass) |  |
| property_id | UUID | no |  |  |
| language_code | VARCHAR(5) | no |  |  |
| title | TEXT | yes |  |  |
| description | TEXT | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |
| address | TEXT | yes |  |  |

Indexes:

- `idx_property_translations_property_lang` on `property_id, language_code`
- `uq_property_translations_property_lang` on `property_id, language_code` unique

### `public.property_views`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| property_id | UUID | yes |  |  |
| user_type | VARCHAR(10) | no |  |  |
| user_id | UUID | yes |  |  |
| viewed_at | TIMESTAMP | no | now() |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Indexes:

- `ix_property_views_property_id` on `property_id`
- `ix_property_views_viewed_at` on `viewed_at`

### `public.social_accounts`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | no |  |  |
| provider | VARCHAR(32) | no |  |  |
| provider_user_id | VARCHAR(255) | no |  |  |
| created_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `ix_social_accounts_user_id` on `user_id`
- `uq_social_accounts_provider_provider_user_id` on `provider, provider_user_id` unique

### `public.user_property_favorites`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no | gen_random_uuid() |  |
| user_id | UUID | no |  |  |
| property_id | UUID | no |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `idx_user_favorites_property_id` on `property_id`
- `idx_user_favorites_user_id` on `user_id`
- `idx_user_favorites_user_property` on `user_id, property_id`
- `user_property_favorites_unique` on `user_id, property_id` unique

### `public.user_roles`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| user_id | UUID | no |  |  |
| role_id | UUID | no |  |  |
| assigned_by | UUID | yes |  |  |
| assigned_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `assigned_by` -> `public.users(id)`
- `role_id` -> `public.roles(id)`
- `user_id` -> `public.users(id)`

### `public.search_fields`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".search_fields_id_seq'::regclass) |  |
| name | VARCHAR(100) | no |  |  |
| field_key | VARCHAR(100) | no |  |  |
| field_type | VARCHAR(50) | yes |  |  |
| is_range | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Indexes:

- `ix_search_fields_id` on `id`
- `search_fields_field_key_key` on `field_key` unique

### `public.property_types`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".property_types_id_seq'::regclass) |  |
| category_id | INTEGER | no |  |  |
| name | VARCHAR(100) | no |  |  |
| slug | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `category_id` -> `public.property_categories(id)`

Indexes:

- `ix_property_types_id` on `id`

### `public.recently_viewed_properties`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | no |  |  |
| property_id | UUID | no |  |  |
| viewed_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `ix_recent_views_user_viewed_at_desc` on `user_id, viewed_at`
- `uq_recent_views_user_property` on `user_id, property_id` unique

### `public.role_permissions`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| role_id | UUID | no |  |  |
| permission_id | UUID | no |  |  |
| created_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `permission_id` -> `public.permissions(id)`
- `role_id` -> `public.roles(id)`

### `public.roles`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| name | VARCHAR(50) | no |  |  |
| description | TEXT | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Indexes:

- `ix_roles_name` on `name` unique

### `public.type_features`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".type_features_id_seq'::regclass) |  |
| property_type_id | INTEGER | no |  |  |
| feature_id | INTEGER | no |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `feature_id` -> `public.features(id)`
- `property_type_id` -> `public.property_types(id)`

Indexes:

- `ix_type_features_id` on `id`

### `public.user_profile_change_challenges`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | no |  |  |
| purpose | VARCHAR(16) | no |  |  |
| new_value | VARCHAR(255) | no |  |  |
| otp_hash | VARCHAR(128) | no |  |  |
| expires_at | TIMESTAMP | no |  |  |
| created_at | TIMESTAMP | no | now() |  |
| cognito_custom_auth_session | TEXT | yes |  |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `ix_user_profile_change_challenges_user_id` on `user_id`

### `public.user_remember_me_sessions`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| user_id | UUID | no |  |  |
| token_hash | VARCHAR(64) | no |  |  |
| cognito_refresh_encrypted | TEXT | no |  |  |
| cognito_username | VARCHAR(255) | no |  |  |
| expires_at | TIMESTAMP | no |  |  |
| revoked_at | TIMESTAMP | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| last_used_at | TIMESTAMP | yes |  |  |
| user_agent | VARCHAR(512) | yes |  |  |
| ip_address | VARCHAR(45) | yes |  |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `ix_user_remember_me_sessions_expires_at` on `expires_at`
- `ix_user_remember_me_sessions_token_hash` on `token_hash` unique
- `ix_user_remember_me_sessions_user_id` on `user_id`

### `public.user_saved_searches`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no | gen_random_uuid() |  |
| user_id | UUID | no |  |  |
| name | VARCHAR(255) | no |  |  |
| search_criteria | JSONB | no |  |  |
| notification_enabled | BOOLEAN | no | false |  |
| last_run_at | TIMESTAMP | yes |  |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `user_id` -> `public.users(id)`

Indexes:

- `idx_user_saved_searches_search_criteria_gin` on `search_criteria`
- `idx_user_saved_searches_user_id` on `user_id`
- `uq_user_saved_searches_user_name` on `user_id, name` unique

### `public.users`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| cognito_sub | VARCHAR(100) | yes |  |  |
| full_name | VARCHAR(255) | no |  |  |
| email | VARCHAR(255) | no |  |  |
| phone_number | VARCHAR(20) | yes |  |  |
| is_active | BOOLEAN | no | true |  |
| is_email_verified | BOOLEAN | no | false |  |
| is_phone_verified | BOOLEAN | no | false |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |
| profile_picture_url | TEXT | yes |  |  |
| deleted_at | TIMESTAMP | yes |  |  |
| deleted_by | UUID | yes |  |  |
| preferred_language | VARCHAR(10) | no |  |  |
| password_login_failed_attempts | INTEGER | no | 0 |  |
| password_login_first_failed_at | TIMESTAMP | yes |  |  |
| password_login_locked_until | TIMESTAMP | yes |  |  |
| agency_id | UUID | yes |  |  |
| password_hash | VARCHAR(255) | yes |  |  |

Foreign keys:

- `agency_id` -> `public.agency_master(id)`
- `deleted_by` -> `public.users(id)`

Indexes:

- `ix_users_agency_id` on `agency_id`
- `ix_users_cognito_sub` on `cognito_sub` unique
- `ix_users_deleted_at` on `deleted_at`
- `ix_users_deleted_by` on `deleted_by`
- `ix_users_email` on `email` unique
- `ix_users_password_login_locked_until` on `password_login_locked_until`
- `ix_users_phone_number` on `phone_number` unique

### `public.areas`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | INTEGER | no | nextval('"public".areas_id_seq'::regclass) |  |
| city_id | INTEGER | no |  |  |
| name | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | yes |  |  |
| created_at | TIMESTAMP | yes | now() |  |
| updated_at | TIMESTAMP | yes | now() |  |

Foreign keys:

- `city_id` -> `public.cities(id)`

Indexes:

- `ix_areas_id` on `id`

### `public.property_owner`

| Column | Type | Nullable | Default | PK |
| --- | --- | --- | --- | --- |
| id | UUID | no |  |  |
| property_id | UUID | no |  |  |
| owner_id | UUID | no |  |  |
| is_active | BOOLEAN | no | false |  |
| created_at | TIMESTAMP | no | now() |  |
| updated_at | TIMESTAMP | no | now() |  |

Foreign keys:

- `owner_id` -> `public.owner(owner_id)`

Indexes:

- `ix_property_owner_owner_id` on `owner_id`
- `ix_property_owner_property_id` on `property_id`
- `uq_property_owner_property_owner` on `property_id, owner_id` unique
