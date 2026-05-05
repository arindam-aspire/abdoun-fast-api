# Database schema (Abdoun FastAPI)

_Generated: 2026-04-29 06:48:37 UTC. Source: introspection of PostgreSQL using `DATABASE_URL` from `.env` (secrets not stored in this file)._

## Connection

- Driver: PostgreSQL (SQLAlchemy / `postgresql+psycopg2` as configured in `.env`).
- Credentials and host are only in `.env`; not duplicated here.

## PostgreSQL extensions

| Extension | Version |
|-----------|---------|
| `pgcrypto` | 1.3 |
| `plpgsql` | 1.0 |
| `postgis` | 3.5.1 |

## Schemas (non-system)

- `public`

## Alembic revision (database)

- `0038_backfill_agent`

## Views

| Schema | Name | Type |
|--------|------|------|
| `public` | `geography_columns` | VIEW |
| `public` | `geometry_columns` | VIEW |

## Sequences

| Schema | Sequence | Data type |
|--------|----------|-----------|
| `public` | `areas_id_seq` | integer |
| `public` | `category_features_id_seq` | integer |
| `public` | `category_search_fields_id_seq` | integer |
| `public` | `cities_id_seq` | integer |
| `public` | `features_id_seq` | integer |
| `public` | `properties_id_seq` | bigint |
| `public` | `property_categories_id_seq` | integer |
| `public` | `property_media_id_seq` | integer |
| `public` | `property_status_id_seq` | integer |
| `public` | `property_translations_id_seq` | integer |
| `public` | `property_types_id_seq` | integer |
| `public` | `search_fields_id_seq` | integer |
| `public` | `type_features_id_seq` | integer |

## Base tables (summary)

- `public.activity_logs`
- `public.admin_agent_assignments`
- `public.agent_invites`
- `public.agent_profiles`
- `public.alembic_version`
- `public.areas`
- `public.category_features`
- `public.category_search_fields`
- `public.cities`
- `public.dashboard_summary`
- `public.features`
- `public.leads`
- `public.owner`
- `public.permissions`
- `public.properties_normalized`
- `public.property_categories`
- `public.property_features`
- `public.property_listing_submissions`
- `public.property_media`
- `public.property_owner`
- `public.property_status`
- `public.property_translations`
- `public.property_types`
- `public.property_views`
- `public.recently_viewed_properties`
- `public.role_permissions`
- `public.roles`
- `public.search_fields`
- `public.spatial_ref_sys`
- `public.type_features`
- `public.user_profile_change_challenges`
- `public.user_property_favorites`
- `public.user_roles`
- `public.user_saved_searches`
- `public.users`

## Foreign keys

| From | Column | To | FK name |
|------|--------|----|---------|
| `public.activity_logs` | `property_id` | `public.properties_normalized` (`id`) | `activity_logs_property_id_fkey` |
| `public.admin_agent_assignments` | `agent_id` | `public.users` (`id`) | `admin_agent_assignments_agent_id_fkey` |
| `public.admin_agent_assignments` | `admin_id` | `public.users` (`id`) | `admin_agent_assignments_admin_id_fkey` |
| `public.agent_invites` | `revoked_by` | `public.users` (`id`) | `fk_agent_invites_revoked_by` |
| `public.agent_invites` | `invited_by` | `public.users` (`id`) | `agent_invites_invited_by_fkey` |
| `public.agent_profiles` | `reviewed_by` | `public.users` (`id`) | `fk_agent_profiles_reviewed_by` |
| `public.agent_profiles` | `approved_by` | `public.users` (`id`) | `agent_profiles_approved_by_fkey` |
| `public.agent_profiles` | `user_id` | `public.users` (`id`) | `agent_profiles_user_id_fkey` |
| `public.agent_profiles` | `deleted_by` | `public.users` (`id`) | `fk_agent_profiles_deleted_by` |
| `public.areas` | `city_id` | `public.cities` (`id`) | `areas_city_id_fkey` |
| `public.category_features` | `category_id` | `public.property_categories` (`id`) | `category_features_category_id_fkey` |
| `public.category_features` | `feature_id` | `public.features` (`id`) | `category_features_feature_id_fkey` |
| `public.category_search_fields` | `field_id` | `public.search_fields` (`id`) | `category_search_fields_field_id_fkey` |
| `public.category_search_fields` | `category_id` | `public.property_categories` (`id`) | `category_search_fields_category_id_fkey` |
| `public.leads` | `property_id` | `public.properties_normalized` (`id`) | `leads_property_id_fkey` |
| `public.owner` | `user_id` | `public.users` (`id`) | `fk_owner_user_id_users` |
| `public.properties_normalized` | `agent_user_id` | `public.users` (`id`) | `fk_properties_agent_user` |
| `public.properties_normalized` | `deleted_by` | `public.users` (`id`) | `fk_properties_normalized_deleted_by_users` |
| `public.properties_normalized` | `category_id` | `public.property_categories` (`id`) | `properties_normalized_category_id_fkey` |
| `public.properties_normalized` | `type_id` | `public.property_types` (`id`) | `properties_normalized_type_id_fkey` |
| `public.properties_normalized` | `property_status_id` | `public.property_status` (`id`) | `properties_normalized_property_status_id_fkey` |
| `public.properties_normalized` | `city_id` | `public.cities` (`id`) | `properties_normalized_city_id_fkey` |
| `public.properties_normalized` | `location_id` | `public.areas` (`id`) | `properties_normalized_location_id_fkey` |
| `public.properties_normalized` | `created_by` | `public.users` (`id`) | `fk_properties_normalized_created_by_users` |
| `public.properties_normalized` | `approved_by_user_id` | `public.users` (`id`) | `fk_properties_approved_by_user` |
| `public.properties_normalized` | `updated_by_user_id` | `public.users` (`id`) | `fk_properties_updated_by_user` |
| `public.property_features` | `feature_id` | `public.features` (`id`) | `property_features_feature_id_fkey` |
| `public.property_features` | `property_id` | `public.properties_normalized` (`id`) | `property_features_property_id_fkey` |
| `public.property_listing_submissions` | `submitted_by` | `public.users` (`id`) | `property_listing_submissions_submitted_by_fkey` |
| `public.property_listing_submissions` | `reviewed_by` | `public.users` (`id`) | `fk_property_listing_submissions_reviewed_by_users` |
| `public.property_listing_submissions` | `deleted_by` | `public.users` (`id`) | `fk_property_listing_submissions_deleted_by_users` |
| `public.property_listing_submissions` | `property_id` | `public.properties_normalized` (`id`) | `property_listing_submissions_property_id_fkey` |
| `public.property_media` | `property_id` | `public.properties_normalized` (`id`) | `property_media_property_id_fkey` |
| `public.property_owner` | `owner_id` | `public.owner` (`owner_id`) | `property_owner_owner_id_fkey` |
| `public.property_owner` | `property_id` | `public.properties_normalized` (`id`) | `property_owner_property_id_fkey` |
| `public.property_translations` | `property_id` | `public.properties_normalized` (`id`) | `property_translations_property_id_fkey` |
| `public.property_types` | `category_id` | `public.property_categories` (`id`) | `property_types_category_id_fkey` |
| `public.property_views` | `property_id` | `public.properties_normalized` (`id`) | `property_views_property_id_fkey` |
| `public.recently_viewed_properties` | `user_id` | `public.users` (`id`) | `recently_viewed_properties_user_id_fkey` |
| `public.recently_viewed_properties` | `property_id` | `public.properties_normalized` (`id`) | `recently_viewed_properties_property_id_fkey` |
| `public.role_permissions` | `role_id` | `public.roles` (`id`) | `role_permissions_role_id_fkey` |
| `public.role_permissions` | `permission_id` | `public.permissions` (`id`) | `role_permissions_permission_id_fkey` |
| `public.type_features` | `property_type_id` | `public.property_types` (`id`) | `type_features_property_type_id_fkey` |
| `public.type_features` | `feature_id` | `public.features` (`id`) | `type_features_feature_id_fkey` |
| `public.user_profile_change_challenges` | `user_id` | `public.users` (`id`) | `user_profile_change_challenges_user_id_fkey` |
| `public.user_property_favorites` | `property_id` | `public.properties_normalized` (`id`) | `user_property_favorites_property_id_fkey` |
| `public.user_property_favorites` | `user_id` | `public.users` (`id`) | `user_property_favorites_user_id_fkey` |
| `public.user_roles` | `user_id` | `public.users` (`id`) | `user_roles_user_id_fkey` |
| `public.user_roles` | `assigned_by` | `public.users` (`id`) | `user_roles_assigned_by_fkey` |
| `public.user_roles` | `role_id` | `public.roles` (`id`) | `user_roles_role_id_fkey` |
| `public.user_saved_searches` | `user_id` | `public.users` (`id`) | `user_saved_searches_user_id_fkey` |
| `public.users` | `deleted_by` | `public.users` (`id`) | `fk_users_deleted_by_users` |

## Indexes (user schemas)


### `public.activity_logs`

- `activity_logs_pkey`: `CREATE UNIQUE INDEX activity_logs_pkey ON public.activity_logs USING btree (id)`
- `ix_activity_logs_created_at`: `CREATE INDEX ix_activity_logs_created_at ON public.activity_logs USING btree (created_at)`
- `ix_activity_logs_user_id`: `CREATE INDEX ix_activity_logs_user_id ON public.activity_logs USING btree (user_id)`

### `public.admin_agent_assignments`

- `admin_agent_assignments_pkey`: `CREATE UNIQUE INDEX admin_agent_assignments_pkey ON public.admin_agent_assignments USING btree (id)`

### `public.agent_invites`

- `agent_invites_pkey`: `CREATE UNIQUE INDEX agent_invites_pkey ON public.agent_invites USING btree (id)`
- `ix_agent_invites_email`: `CREATE INDEX ix_agent_invites_email ON public.agent_invites USING btree (email)`
- `ix_agent_invites_token`: `CREATE UNIQUE INDEX ix_agent_invites_token ON public.agent_invites USING btree (token)`

### `public.agent_profiles`

- `agent_profiles_pkey`: `CREATE UNIQUE INDEX agent_profiles_pkey ON public.agent_profiles USING btree (user_id)`
- `ix_agent_profiles_deleted_at`: `CREATE INDEX ix_agent_profiles_deleted_at ON public.agent_profiles USING btree (deleted_at)`
- `ix_agent_profiles_status`: `CREATE INDEX ix_agent_profiles_status ON public.agent_profiles USING btree (status)`

### `public.alembic_version`

- `alembic_version_pkc`: `CREATE UNIQUE INDEX alembic_version_pkc ON public.alembic_version USING btree (version_num)`

### `public.areas`

- `areas_pkey`: `CREATE UNIQUE INDEX areas_pkey ON public.areas USING btree (id)`
- `ix_areas_id`: `CREATE INDEX ix_areas_id ON public.areas USING btree (id)`

### `public.category_features`

- `category_features_pkey`: `CREATE UNIQUE INDEX category_features_pkey ON public.category_features USING btree (id)`
- `ix_category_features_id`: `CREATE INDEX ix_category_features_id ON public.category_features USING btree (id)`

### `public.category_search_fields`

- `category_search_fields_pkey`: `CREATE UNIQUE INDEX category_search_fields_pkey ON public.category_search_fields USING btree (id)`
- `ix_category_search_fields_id`: `CREATE INDEX ix_category_search_fields_id ON public.category_search_fields USING btree (id)`

### `public.cities`

- `cities_pkey`: `CREATE UNIQUE INDEX cities_pkey ON public.cities USING btree (id)`
- `ix_cities_id`: `CREATE INDEX ix_cities_id ON public.cities USING btree (id)`

### `public.dashboard_summary`

- `dashboard_summary_pkey`: `CREATE UNIQUE INDEX dashboard_summary_pkey ON public.dashboard_summary USING btree (id)`
- `ix_dashboard_summary_last_updated`: `CREATE INDEX ix_dashboard_summary_last_updated ON public.dashboard_summary USING btree (last_updated)`
- `ix_dashboard_summary_user_id`: `CREATE INDEX ix_dashboard_summary_user_id ON public.dashboard_summary USING btree (user_id)`

### `public.features`

- `features_pkey`: `CREATE UNIQUE INDEX features_pkey ON public.features USING btree (id)`
- `features_slug_key`: `CREATE UNIQUE INDEX features_slug_key ON public.features USING btree (slug)`
- `ix_features_id`: `CREATE INDEX ix_features_id ON public.features USING btree (id)`

### `public.leads`

- `ix_leads_created_at`: `CREATE INDEX ix_leads_created_at ON public.leads USING btree (created_at)`
- `ix_leads_property_id`: `CREATE INDEX ix_leads_property_id ON public.leads USING btree (property_id)`
- `leads_pkey`: `CREATE UNIQUE INDEX leads_pkey ON public.leads USING btree (id)`

### `public.owner`

- `ix_owner_email`: `CREATE INDEX ix_owner_email ON public.owner USING btree (email)`
- `ix_owner_phone`: `CREATE INDEX ix_owner_phone ON public.owner USING btree (phone)`
- `ix_owner_user_id`: `CREATE INDEX ix_owner_user_id ON public.owner USING btree (user_id)`
- `owner_pkey`: `CREATE UNIQUE INDEX owner_pkey ON public.owner USING btree (owner_id)`

### `public.permissions`

- `ix_permissions_code`: `CREATE UNIQUE INDEX ix_permissions_code ON public.permissions USING btree (code)`
- `permissions_pkey`: `CREATE UNIQUE INDEX permissions_pkey ON public.permissions USING btree (id)`

### `public.properties_normalized`

- `idx_properties_normalized_location`: `CREATE INDEX idx_properties_normalized_location ON public.properties_normalized USING gist (location)`
- `idx_properties_normalized_reference_number`: `CREATE INDEX idx_properties_normalized_reference_number ON public.properties_normalized USING btree (reference_number)`
- `ix_properties_agent_user_id`: `CREATE INDEX ix_properties_agent_user_id ON public.properties_normalized USING btree (agent_user_id)`
- `ix_properties_approved_by_user_id`: `CREATE INDEX ix_properties_approved_by_user_id ON public.properties_normalized USING btree (approved_by_user_id)`
- `ix_properties_normalized_created_by`: `CREATE INDEX ix_properties_normalized_created_by ON public.properties_normalized USING btree (created_by)`
- `ix_properties_normalized_deleted_at`: `CREATE INDEX ix_properties_normalized_deleted_at ON public.properties_normalized USING btree (deleted_at)`
- `ix_properties_normalized_deleted_by`: `CREATE INDEX ix_properties_normalized_deleted_by ON public.properties_normalized USING btree (deleted_by)`
- `ix_properties_normalized_location_name`: `CREATE INDEX ix_properties_normalized_location_name ON public.properties_normalized USING btree (location_name)`
- `ix_properties_normalized_property_hash`: `CREATE INDEX ix_properties_normalized_property_hash ON public.properties_normalized USING btree (property_hash)`
- `ix_properties_normalized_url`: `CREATE UNIQUE INDEX ix_properties_normalized_url ON public.properties_normalized USING btree (url)`
- `ix_properties_updated_by_user_id`: `CREATE INDEX ix_properties_updated_by_user_id ON public.properties_normalized USING btree (updated_by_user_id)`
- `properties_normalized_pkey`: `CREATE UNIQUE INDEX properties_normalized_pkey ON public.properties_normalized USING btree (id)`

### `public.property_categories`

- `ix_property_categories_id`: `CREATE INDEX ix_property_categories_id ON public.property_categories USING btree (id)`
- `property_categories_pkey`: `CREATE UNIQUE INDEX property_categories_pkey ON public.property_categories USING btree (id)`
- `property_categories_slug_key`: `CREATE UNIQUE INDEX property_categories_slug_key ON public.property_categories USING btree (slug)`

### `public.property_features`

- `property_features_pkey`: `CREATE UNIQUE INDEX property_features_pkey ON public.property_features USING btree (property_id, feature_id)`

### `public.property_listing_submissions`

- `ix_property_listing_submissions_deleted_at`: `CREATE INDEX ix_property_listing_submissions_deleted_at ON public.property_listing_submissions USING btree (deleted_at)`
- `ix_property_listing_submissions_deleted_by`: `CREATE INDEX ix_property_listing_submissions_deleted_by ON public.property_listing_submissions USING btree (deleted_by)`
- `ix_property_listing_submissions_property_id`: `CREATE INDEX ix_property_listing_submissions_property_id ON public.property_listing_submissions USING btree (property_id)`
- `ix_property_listing_submissions_reviewed_by`: `CREATE INDEX ix_property_listing_submissions_reviewed_by ON public.property_listing_submissions USING btree (reviewed_by)`
- `ix_property_listing_submissions_status`: `CREATE INDEX ix_property_listing_submissions_status ON public.property_listing_submissions USING btree (status)`
- `ix_property_listing_submissions_submitted_by`: `CREATE INDEX ix_property_listing_submissions_submitted_by ON public.property_listing_submissions USING btree (submitted_by)`
- `property_listing_submissions_pkey`: `CREATE UNIQUE INDEX property_listing_submissions_pkey ON public.property_listing_submissions USING btree (id)`

### `public.property_media`

- `idx_property_media_property_id`: `CREATE INDEX idx_property_media_property_id ON public.property_media USING btree (property_id)`
- `idx_property_media_property_type_order`: `CREATE INDEX idx_property_media_property_type_order ON public.property_media USING btree (property_id, media_type, display_order)`
- `property_media_pkey`: `CREATE UNIQUE INDEX property_media_pkey ON public.property_media USING btree (id)`

### `public.property_owner`

- `ix_property_owner_owner_id`: `CREATE INDEX ix_property_owner_owner_id ON public.property_owner USING btree (owner_id)`
- `ix_property_owner_property_id`: `CREATE INDEX ix_property_owner_property_id ON public.property_owner USING btree (property_id)`
- `property_owner_pkey`: `CREATE UNIQUE INDEX property_owner_pkey ON public.property_owner USING btree (id)`
- `uq_property_owner_property_owner`: `CREATE UNIQUE INDEX uq_property_owner_property_owner ON public.property_owner USING btree (property_id, owner_id)`

### `public.property_status`

- `ix_property_status_id`: `CREATE INDEX ix_property_status_id ON public.property_status USING btree (id)`
- `property_status_pkey`: `CREATE UNIQUE INDEX property_status_pkey ON public.property_status USING btree (id)`
- `property_status_slug_key`: `CREATE UNIQUE INDEX property_status_slug_key ON public.property_status USING btree (slug)`

### `public.property_translations`

- `idx_property_translations_property_lang`: `CREATE INDEX idx_property_translations_property_lang ON public.property_translations USING btree (property_id, language_code)`
- `property_translations_pkey`: `CREATE UNIQUE INDEX property_translations_pkey ON public.property_translations USING btree (id)`
- `uq_property_translations_property_lang`: `CREATE UNIQUE INDEX uq_property_translations_property_lang ON public.property_translations USING btree (property_id, language_code)`

### `public.property_types`

- `ix_property_types_id`: `CREATE INDEX ix_property_types_id ON public.property_types USING btree (id)`
- `property_types_pkey`: `CREATE UNIQUE INDEX property_types_pkey ON public.property_types USING btree (id)`

### `public.property_views`

- `ix_property_views_property_id`: `CREATE INDEX ix_property_views_property_id ON public.property_views USING btree (property_id)`
- `ix_property_views_viewed_at`: `CREATE INDEX ix_property_views_viewed_at ON public.property_views USING btree (viewed_at)`
- `property_views_pkey`: `CREATE UNIQUE INDEX property_views_pkey ON public.property_views USING btree (id)`

### `public.recently_viewed_properties`

- `ix_recent_views_user_viewed_at_desc`: `CREATE INDEX ix_recent_views_user_viewed_at_desc ON public.recently_viewed_properties USING btree (user_id, viewed_at DESC)`
- `recently_viewed_properties_pkey`: `CREATE UNIQUE INDEX recently_viewed_properties_pkey ON public.recently_viewed_properties USING btree (id)`
- `uq_recent_views_user_property`: `CREATE UNIQUE INDEX uq_recent_views_user_property ON public.recently_viewed_properties USING btree (user_id, property_id)`

### `public.role_permissions`

- `role_permissions_pkey`: `CREATE UNIQUE INDEX role_permissions_pkey ON public.role_permissions USING btree (role_id, permission_id)`

### `public.roles`

- `ix_roles_name`: `CREATE UNIQUE INDEX ix_roles_name ON public.roles USING btree (name)`
- `roles_pkey`: `CREATE UNIQUE INDEX roles_pkey ON public.roles USING btree (id)`

### `public.search_fields`

- `ix_search_fields_id`: `CREATE INDEX ix_search_fields_id ON public.search_fields USING btree (id)`
- `search_fields_field_key_key`: `CREATE UNIQUE INDEX search_fields_field_key_key ON public.search_fields USING btree (field_key)`
- `search_fields_pkey`: `CREATE UNIQUE INDEX search_fields_pkey ON public.search_fields USING btree (id)`

### `public.spatial_ref_sys`

- `spatial_ref_sys_pkey`: `CREATE UNIQUE INDEX spatial_ref_sys_pkey ON public.spatial_ref_sys USING btree (srid)`

### `public.type_features`

- `ix_type_features_id`: `CREATE INDEX ix_type_features_id ON public.type_features USING btree (id)`
- `type_features_pkey`: `CREATE UNIQUE INDEX type_features_pkey ON public.type_features USING btree (id)`

### `public.user_profile_change_challenges`

- `ix_user_profile_change_challenges_user_id`: `CREATE INDEX ix_user_profile_change_challenges_user_id ON public.user_profile_change_challenges USING btree (user_id)`
- `user_profile_change_challenges_pkey`: `CREATE UNIQUE INDEX user_profile_change_challenges_pkey ON public.user_profile_change_challenges USING btree (id)`

### `public.user_property_favorites`

- `idx_user_favorites_property_id`: `CREATE INDEX idx_user_favorites_property_id ON public.user_property_favorites USING btree (property_id)`
- `idx_user_favorites_user_id`: `CREATE INDEX idx_user_favorites_user_id ON public.user_property_favorites USING btree (user_id)`
- `idx_user_favorites_user_property`: `CREATE INDEX idx_user_favorites_user_property ON public.user_property_favorites USING btree (user_id, property_id)`
- `user_property_favorites_pkey`: `CREATE UNIQUE INDEX user_property_favorites_pkey ON public.user_property_favorites USING btree (id)`
- `user_property_favorites_unique`: `CREATE UNIQUE INDEX user_property_favorites_unique ON public.user_property_favorites USING btree (user_id, property_id)`

### `public.user_roles`

- `user_roles_pkey`: `CREATE UNIQUE INDEX user_roles_pkey ON public.user_roles USING btree (user_id, role_id)`

### `public.user_saved_searches`

- `idx_user_saved_searches_search_criteria_gin`: `CREATE INDEX idx_user_saved_searches_search_criteria_gin ON public.user_saved_searches USING gin (search_criteria)`
- `idx_user_saved_searches_user_id`: `CREATE INDEX idx_user_saved_searches_user_id ON public.user_saved_searches USING btree (user_id)`
- `uq_user_saved_searches_user_name`: `CREATE UNIQUE INDEX uq_user_saved_searches_user_name ON public.user_saved_searches USING btree (user_id, name)`
- `user_saved_searches_pkey`: `CREATE UNIQUE INDEX user_saved_searches_pkey ON public.user_saved_searches USING btree (id)`

### `public.users`

- `ix_users_cognito_sub`: `CREATE UNIQUE INDEX ix_users_cognito_sub ON public.users USING btree (cognito_sub)`
- `ix_users_deleted_at`: `CREATE INDEX ix_users_deleted_at ON public.users USING btree (deleted_at)`
- `ix_users_deleted_by`: `CREATE INDEX ix_users_deleted_by ON public.users USING btree (deleted_by)`
- `ix_users_email`: `CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email)`
- `ix_users_phone_number`: `CREATE UNIQUE INDEX ix_users_phone_number ON public.users USING btree (phone_number)`
- `users_pkey`: `CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)`

## Columns by table

### `public.activity_logs`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `user_id` | uuid | `uuid` | YES | — |
| 3 | `property_id` | uuid | `uuid` | YES | — |
| 4 | `activity_type` | character varying | `varchar` | YES | — |
| 5 | `message` | text | `text` | YES | — |
| 6 | `tone` | character varying | `varchar` | YES | — |
| 7 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 8 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.admin_agent_assignments`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `admin_id` | uuid | `uuid` | NO | — |
| 3 | `agent_id` | uuid | `uuid` | NO | — |
| 4 | `is_active` | boolean | `bool` | NO | true |
| 5 | `assigned_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 6 | `revoked_at` | timestamp with time zone | `timestamptz` | YES | — |
| 7 | `can_inherit_privileges` | boolean | `bool` | NO | false |

### `public.agent_invites`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `email` | character varying | `varchar` | NO | — |
| 3 | `invited_by` | uuid | `uuid` | NO | — |
| 4 | `token` | character varying | `varchar` | NO | — |
| 5 | `expires_at` | timestamp with time zone | `timestamptz` | NO | — |
| 6 | `is_used` | boolean | `bool` | NO | false |
| 7 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 8 | `invited_at` | timestamp with time zone | `timestamptz` | YES | now() |
| 9 | `revoked_at` | timestamp with time zone | `timestamptz` | YES | — |
| 10 | `revoked_by` | uuid | `uuid` | YES | — |

### `public.agent_profiles`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `user_id` | uuid | `uuid` | NO | — |
| 2 | `service_area` | character varying | `varchar` | YES | — |
| 3 | `approved_by` | uuid | `uuid` | YES | — |
| 4 | `approved_at` | timestamp with time zone | `timestamptz` | YES | — |
| 5 | `status` | character varying | `varchar` | NO | 'INVITED'::character varying |
| 8 | `reviewed_by` | uuid | `uuid` | YES | — |
| 9 | `reviewed_at` | timestamp with time zone | `timestamptz` | YES | — |
| 10 | `form_submitted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 11 | `password_set_at` | timestamp with time zone | `timestamptz` | YES | — |
| 12 | `decline_reason` | text | `text` | YES | — |
| 13 | `deleted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 14 | `deleted_by` | uuid | `uuid` | YES | — |
| 15 | `status_reason` | text | `text` | YES | — |

### `public.alembic_version`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `version_num` | character varying | `varchar` | NO | — |

### `public.areas`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('areas_id_seq'::regclass) |
| 2 | `city_id` | integer | `int4` | NO | — |
| 3 | `name` | character varying | `varchar` | NO | — |
| 4 | `is_active` | boolean | `bool` | YES | — |
| 5 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 6 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.category_features`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('category_features_id_seq'::regclass) |
| 2 | `category_id` | integer | `int4` | NO | — |
| 3 | `feature_id` | integer | `int4` | NO | — |
| 4 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 5 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.category_search_fields`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('category_search_fields_id_seq'::regclass) |
| 2 | `category_id` | integer | `int4` | NO | — |
| 3 | `field_id` | integer | `int4` | NO | — |
| 4 | `is_required` | boolean | `bool` | YES | — |
| 5 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 6 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.cities`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('cities_id_seq'::regclass) |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `is_active` | boolean | `bool` | YES | — |
| 4 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 5 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.dashboard_summary`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `user_id` | uuid | `uuid` | YES | — |
| 3 | `total_properties` | integer | `int4` | YES | — |
| 4 | `active_properties` | integer | `int4` | YES | — |
| 5 | `draft_properties` | integer | `int4` | YES | — |
| 6 | `total_views` | integer | `int4` | YES | — |
| 7 | `total_inquiries` | integer | `int4` | YES | — |
| 8 | `total_deals` | integer | `int4` | YES | — |
| 9 | `conversion_rate` | numeric | `numeric` | YES | — |
| 10 | `last_updated` | timestamp with time zone | `timestamptz` | YES | — |
| 11 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 12 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.features`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('features_id_seq'::regclass) |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `slug` | character varying | `varchar` | NO | — |
| 4 | `is_active` | boolean | `bool` | YES | — |
| 5 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 6 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.leads`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `property_id` | uuid | `uuid` | YES | — |
| 3 | `user_id` | uuid | `uuid` | YES | — |
| 4 | `inquiry_type` | character varying | `varchar` | YES | — |
| 5 | `message` | text | `text` | YES | — |
| 6 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 7 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.owner`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `owner_id` | uuid | `uuid` | NO | — |
| 2 | `full_name` | character varying | `varchar` | YES | — |
| 3 | `email` | character varying | `varchar` | YES | — |
| 4 | `phone` | character varying | `varchar` | YES | — |
| 5 | `nationality` | character varying | `varchar` | YES | — |
| 6 | `ssi` | character varying | `varchar` | YES | — |
| 7 | `address` | text | `text` | YES | — |
| 8 | `documents` | jsonb | `jsonb` | NO | '[]'::jsonb |
| 9 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 10 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 11 | `user_id` | uuid | `uuid` | YES | — |

### `public.permissions`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `code` | character varying | `varchar` | NO | — |
| 3 | `description` | text | `text` | YES | — |
| 4 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.properties_normalized`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `category_id` | integer | `int4` | NO | — |
| 3 | `type_id` | integer | `int4` | NO | — |
| 4 | `property_status_id` | integer | `int4` | NO | — |
| 5 | `city_id` | integer | `int4` | NO | — |
| 6 | `location_id` | integer | `int4` | NO | — |
| 7 | `url` | character varying | `varchar` | YES | — |
| 8 | `title` | character varying | `varchar` | NO | — |
| 9 | `description` | character varying | `varchar` | YES | — |
| 10 | `is_exclusive` | boolean | `bool` | YES | — |
| 11 | `is_featured` | boolean | `bool` | YES | — |
| 12 | `is_verified` | boolean | `bool` | YES | — |
| 13 | `latitude` | numeric | `numeric` | YES | — |
| 14 | `longitude` | numeric | `numeric` | YES | — |
| 15 | `location` | USER-DEFINED | `geometry` | YES | — |
| 16 | `location_name` | character varying | `varchar` | YES | — |
| 17 | `price` | numeric | `numeric` | NO | — |
| 18 | `selling_price_amount` | numeric | `numeric` | YES | — |
| 19 | `selling_price_currency` | character varying | `varchar` | YES | — |
| 20 | `rent_price_amount` | numeric | `numeric` | YES | — |
| 21 | `rent_price_currency` | character varying | `varchar` | YES | — |
| 22 | `area` | numeric | `numeric` | YES | — |
| 23 | `plot_area` | numeric | `numeric` | YES | — |
| 24 | `bedrooms` | integer | `int4` | YES | — |
| 25 | `bathrooms` | integer | `int4` | YES | — |
| 26 | `rooms` | integer | `int4` | YES | — |
| 27 | `furniture_status` | character varying | `varchar` | YES | — |
| 28 | `parking` | boolean | `bool` | YES | — |
| 29 | `property_age` | integer | `int4` | YES | — |
| 30 | `images` | character varying | `varchar` | YES | — |
| 31 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 32 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |
| 33 | `more_features` | json | `json` | YES | — |
| 34 | `reference_number` | character varying | `varchar` | YES | — |
| 35 | `currency` | character varying | `varchar` | YES | — |
| 36 | `rent_commission_percent` | numeric | `numeric` | YES | — |
| 37 | `contract_duration` | character varying | `varchar` | YES | — |
| 38 | `payment_method` | character varying | `varchar` | YES | — |
| 39 | `property_hash` | integer | `int4` | NO | — |
| 40 | `virtual_tour_url` | text | `text` | YES | — |
| 41 | `updated_by_user_id` | uuid | `uuid` | YES | — |
| 42 | `agent_user_id` | uuid | `uuid` | YES | — |
| 43 | `approved_by_user_id` | uuid | `uuid` | YES | — |
| 44 | `deal_closed` | boolean | `bool` | NO | false |
| 45 | `listing_purpose` | character varying | `varchar` | YES | — |
| 46 | `address` | text | `text` | YES | — |
| 47 | `parking_spaces` | integer | `int4` | YES | — |
| 48 | `total_floors` | integer | `int4` | YES | — |
| 49 | `completion_status` | character varying | `varchar` | YES | — |
| 50 | `occupancy` | character varying | `varchar` | YES | — |
| 51 | `ownership_type` | character varying | `varchar` | YES | — |
| 52 | `permit_number` | character varying | `varchar` | YES | — |
| 53 | `orientation` | character varying | `varchar` | YES | — |
| 54 | `service_charge` | numeric | `numeric` | YES | — |
| 55 | `maintenance_fee` | numeric | `numeric` | YES | — |
| 56 | `youtube_url` | text | `text` | YES | — |
| 57 | `created_by` | uuid | `uuid` | YES | — |
| 58 | `deleted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 59 | `deleted_by` | uuid | `uuid` | YES | — |
| 60 | `delete_reason` | text | `text` | YES | — |

### `public.property_categories`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('property_categories_id_seq'::regclass) |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `slug` | character varying | `varchar` | NO | — |
| 4 | `is_active` | boolean | `bool` | YES | — |
| 5 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 6 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.property_features`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `property_id` | uuid | `uuid` | NO | — |
| 2 | `feature_id` | integer | `int4` | NO | — |
| 3 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 4 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |
| 5 | `value` | character varying | `varchar` | YES | — |

### `public.property_listing_submissions`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | gen_random_uuid() |
| 2 | `submitted_by` | uuid | `uuid` | NO | — |
| 3 | `property_id` | uuid | `uuid` | YES | — |
| 4 | `status` | character varying | `varchar` | NO | 'draft'::character varying |
| 5 | `current_step` | integer | `int4` | NO | 1 |
| 6 | `last_completed_step` | integer | `int4` | NO | 0 |
| 7 | `payload` | jsonb | `jsonb` | NO | '{}'::jsonb |
| 8 | `step_completion` | jsonb | `jsonb` | NO | '{}'::jsonb |
| 9 | `terms_accepted` | boolean | `bool` | NO | false |
| 10 | `privacy_accepted` | boolean | `bool` | NO | false |
| 11 | `public_display_authorized` | boolean | `bool` | NO | false |
| 12 | `fees_acknowledged` | boolean | `bool` | NO | false |
| 13 | `submitted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 14 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 15 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 16 | `reviewed_by` | uuid | `uuid` | YES | — |
| 17 | `reviewed_at` | timestamp with time zone | `timestamptz` | YES | — |
| 18 | `review_reason` | text | `text` | YES | — |
| 19 | `deleted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 20 | `deleted_by` | uuid | `uuid` | YES | — |
| 21 | `delete_reason` | text | `text` | YES | — |

### `public.property_media`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('property_media_id_seq'::regclass) |
| 2 | `property_id` | uuid | `uuid` | NO | — |
| 3 | `media_type` | character varying | `varchar` | NO | — |
| 4 | `url` | text | `text` | NO | — |
| 5 | `thumb_url` | text | `text` | YES | — |
| 6 | `is_primary` | boolean | `bool` | YES | false |
| 7 | `display_order` | integer | `int4` | YES | 0 |
| 8 | `caption` | text | `text` | YES | — |
| 9 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 10 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.property_owner`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `property_id` | uuid | `uuid` | NO | — |
| 3 | `owner_id` | uuid | `uuid` | NO | — |
| 4 | `is_active` | boolean | `bool` | NO | false |
| 5 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 6 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.property_status`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('property_status_id_seq'::regclass) |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `slug` | character varying | `varchar` | NO | — |
| 4 | `is_active` | boolean | `bool` | YES | — |
| 5 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 6 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.property_translations`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('property_translations_id_seq'::regclass) |
| 2 | `property_id` | uuid | `uuid` | NO | — |
| 3 | `language_code` | character varying | `varchar` | NO | — |
| 4 | `title` | text | `text` | YES | — |
| 5 | `description` | text | `text` | YES | — |
| 6 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 7 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |
| 8 | `address` | text | `text` | YES | — |

### `public.property_types`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('property_types_id_seq'::regclass) |
| 2 | `category_id` | integer | `int4` | NO | — |
| 3 | `name` | character varying | `varchar` | NO | — |
| 4 | `slug` | character varying | `varchar` | NO | — |
| 5 | `is_active` | boolean | `bool` | YES | — |
| 6 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 7 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.property_views`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `property_id` | uuid | `uuid` | YES | — |
| 3 | `user_type` | USER-DEFINED | `property_view_user_type` | NO | — |
| 4 | `user_id` | uuid | `uuid` | YES | — |
| 5 | `viewed_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 6 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 7 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.recently_viewed_properties`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `user_id` | uuid | `uuid` | NO | — |
| 3 | `property_id` | uuid | `uuid` | NO | — |
| 4 | `viewed_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.role_permissions`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `role_id` | uuid | `uuid` | NO | — |
| 2 | `permission_id` | uuid | `uuid` | NO | — |
| 3 | `created_at` | timestamp with time zone | `timestamptz` | YES | now() |

### `public.roles`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `description` | text | `text` | YES | — |
| 4 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 5 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.search_fields`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('search_fields_id_seq'::regclass) |
| 2 | `name` | character varying | `varchar` | NO | — |
| 3 | `field_key` | character varying | `varchar` | NO | — |
| 4 | `field_type` | character varying | `varchar` | YES | — |
| 5 | `is_range` | boolean | `bool` | YES | — |
| 6 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 7 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.spatial_ref_sys`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `srid` | integer | `int4` | NO | — |
| 2 | `auth_name` | character varying | `varchar` | YES | — |
| 3 | `auth_srid` | integer | `int4` | YES | — |
| 4 | `srtext` | character varying | `varchar` | YES | — |
| 5 | `proj4text` | character varying | `varchar` | YES | — |

### `public.type_features`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | integer | `int4` | NO | nextval('type_features_id_seq'::regclass) |
| 2 | `property_type_id` | integer | `int4` | NO | — |
| 3 | `feature_id` | integer | `int4` | NO | — |
| 4 | `created_at` | timestamp without time zone | `timestamp` | YES | now() |
| 5 | `updated_at` | timestamp without time zone | `timestamp` | YES | now() |

### `public.user_profile_change_challenges`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `user_id` | uuid | `uuid` | NO | — |
| 3 | `purpose` | character varying | `varchar` | NO | — |
| 4 | `new_value` | character varying | `varchar` | NO | — |
| 5 | `otp_hash` | character varying | `varchar` | NO | — |
| 6 | `expires_at` | timestamp with time zone | `timestamptz` | NO | — |
| 7 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 8 | `cognito_custom_auth_session` | text | `text` | YES | — |

### `public.user_property_favorites`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | gen_random_uuid() |
| 2 | `user_id` | uuid | `uuid` | NO | — |
| 3 | `property_id` | uuid | `uuid` | NO | — |
| 4 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 5 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.user_roles`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `user_id` | uuid | `uuid` | NO | — |
| 2 | `role_id` | uuid | `uuid` | NO | — |
| 3 | `assigned_by` | uuid | `uuid` | YES | — |
| 4 | `assigned_at` | timestamp with time zone | `timestamptz` | YES | now() |

### `public.user_saved_searches`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | gen_random_uuid() |
| 2 | `user_id` | uuid | `uuid` | NO | — |
| 3 | `name` | character varying | `varchar` | NO | — |
| 4 | `search_criteria` | jsonb | `jsonb` | NO | — |
| 5 | `notification_enabled` | boolean | `bool` | NO | false |
| 6 | `last_run_at` | timestamp with time zone | `timestamptz` | YES | — |
| 7 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 8 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |

### `public.users`

| # | Column | Data type | UDT | Nullable | Default |
|---|--------|-----------|-----|----------|---------|
| 1 | `id` | uuid | `uuid` | NO | — |
| 2 | `cognito_sub` | character varying | `varchar` | YES | — |
| 3 | `full_name` | character varying | `varchar` | NO | — |
| 4 | `email` | character varying | `varchar` | NO | — |
| 5 | `phone_number` | character varying | `varchar` | YES | — |
| 6 | `is_active` | boolean | `bool` | NO | true |
| 7 | `is_email_verified` | boolean | `bool` | NO | false |
| 8 | `is_phone_verified` | boolean | `bool` | NO | false |
| 9 | `created_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 10 | `updated_at` | timestamp with time zone | `timestamptz` | NO | now() |
| 11 | `profile_picture_url` | text | `text` | YES | — |
| 12 | `deleted_at` | timestamp with time zone | `timestamptz` | YES | — |
| 13 | `deleted_by` | uuid | `uuid` | YES | — |

## Application models in this repo (SQLAlchemy)

The codebase under `app/models/` currently declares **`Property`** mapped to table **`properties`** (integer `id`, PostGIS `location`, JSON fields, etc.). The live database inspected here has **no `properties` table**; listings use **`properties_normalized`** and many other tables. Alembic revisions in `alembic/versions/` may not match `alembic_version` above if migrations are maintained elsewhere.
