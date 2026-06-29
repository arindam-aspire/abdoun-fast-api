"""align dco taxonomy and agency workflow schema

Revision ID: 0056_dco_taxonomy_workflows
Revises: 0055_user_agency_mappings
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0056_dco_taxonomy_workflows"
down_revision = "0055_user_agency_mappings"
branch_labels = None
depends_on = None


def _upsert_category(slug: str, name: str) -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO property_categories (name, slug, is_active, created_at, updated_at)
            VALUES (:name, :slug, true, now(), now())
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                is_active = true,
                updated_at = now()
            """
        ).bindparams(name=name, slug=slug)
    )


def _upsert_property_type(category_slug: str, legacy_slugs: tuple[str, ...], slug: str, name: str) -> None:
    legacy_list = ", ".join(f"'{value}'" for value in legacy_slugs)
    op.execute(
        f"""
        WITH category_row AS (
            SELECT id FROM property_categories WHERE slug = '{category_slug}' LIMIT 1
        ),
        existing_type AS (
            SELECT pt.id
            FROM property_types pt
            JOIN category_row cr ON cr.id = pt.category_id
            WHERE pt.slug IN ({legacy_list})
            ORDER BY CASE WHEN pt.slug = '{slug}' THEN 0 ELSE 1 END, pt.id
            LIMIT 1
        ),
        updated_type AS (
            UPDATE property_types pt
            SET name = '{name}',
                slug = '{slug}',
                is_active = true,
                updated_at = now()
            FROM existing_type et
            WHERE pt.id = et.id
            RETURNING pt.id
        )
        INSERT INTO property_types (category_id, name, slug, is_active, created_at, updated_at)
        SELECT cr.id, '{name}', '{slug}', true, now(), now()
        FROM category_row cr
        WHERE NOT EXISTS (SELECT 1 FROM updated_type)
        """
    )


def _upsert_property_status(slug: str, name: str, legacy_slugs: tuple[str, ...] = ()) -> None:
    all_slugs = (slug, *legacy_slugs)
    slug_list = ", ".join(f"'{value}'" for value in all_slugs)
    op.execute(
        f"""
        WITH existing_status AS (
            SELECT id
            FROM property_status
            WHERE slug IN ({slug_list})
            ORDER BY CASE WHEN slug = '{slug}' THEN 0 ELSE 1 END, id
            LIMIT 1
        ),
        updated_status AS (
            UPDATE property_status ps
            SET name = '{name}',
                slug = '{slug}',
                is_active = true,
                updated_at = now()
            FROM existing_status es
            WHERE ps.id = es.id
            RETURNING ps.id
        )
        INSERT INTO property_status (name, slug, is_active, created_at, updated_at)
        SELECT '{name}', '{slug}', true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM updated_status)
        """
    )


def upgrade() -> None:
    op.add_column(
        "agency_master",
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_APPROVAL"),
    )
    op.execute(
        """
        UPDATE agency_master
        SET status = CASE
            WHEN is_active IS TRUE AND is_verified IS TRUE THEN 'ACTIVE'
            WHEN is_active IS FALSE AND is_verified IS FALSE THEN 'PENDING_APPROVAL'
            ELSE 'PENDING_APPROVAL'
        END
        """
    )
    op.create_index("ix_agency_master_status", "agency_master", ["status"])

    op.create_table(
        "agency_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("agency_name", sa.String(length=255), nullable=True),
        sa.Column("agency_trade_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="INVITED"),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("accepted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agency_invitations_email_status", "agency_invitations", ["email", "status"])
    op.create_index("ix_agency_invitations_token", "agency_invitations", ["token"], unique=True)

    for slug, name in (
        ("residential", "Residential"),
        ("commercial", "Commercial"),
        ("land", "Land"),
    ):
        _upsert_category(slug, name)

    taxonomy = {
        "residential": (
            (("apartment", "apartments"), "apartments", "Apartments"),
            (("villa", "villas"), "villas", "Villas"),
            (("building", "buildings"), "buildings", "Buildings"),
            (("farm", "farms"), "farms", "Farms"),
        ),
        "commercial": (
            (("office", "offices"), "offices", "Offices"),
            (("showroom", "showrooms"), "showrooms", "Showrooms"),
            (("building", "buildings"), "buildings", "Buildings"),
            (("warehouse",), "warehouse", "Warehouse"),
            (("business", "businesses"), "businesses", "Businesses"),
            (("villa", "villas"), "villas", "Villas"),
        ),
        "land": (
            (("residential-land", "residential-lands"), "residential-lands", "Residential Lands"),
            (("commercial-land", "commercial-lands"), "commercial-lands", "Commercial Lands"),
            (("industrial-land", "industrial-lands"), "industrial-lands", "Industrial Lands"),
            (("agricultural-land", "agricultural-lands"), "agricultural-lands", "Agricultural Lands"),
            (("mixed-use-land", "mixed-use-lands"), "mixed-use-lands", "Mixed Use Lands"),
        ),
    }
    for category_slug, property_types in taxonomy.items():
        for legacy_slugs, slug, name in property_types:
            _upsert_property_type(category_slug, legacy_slugs, slug, name)

    op.execute(
        """
        UPDATE property_types pt
        SET is_active = false,
            updated_at = now()
        FROM property_categories pc
        WHERE pc.id = pt.category_id
          AND (
            (pc.slug = 'residential' AND pt.slug NOT IN ('apartments', 'villas', 'buildings', 'farms'))
            OR (pc.slug = 'commercial' AND pt.slug NOT IN ('offices', 'showrooms', 'buildings', 'warehouse', 'businesses', 'villas'))
            OR (pc.slug = 'land' AND pt.slug NOT IN ('residential-lands', 'commercial-lands', 'industrial-lands', 'agricultural-lands', 'mixed-use-lands'))
          )
        """
    )

    _upsert_property_status("draft", "Draft")
    _upsert_property_status("pending-approval", "Pending Approval", ("pending",))
    _upsert_property_status("approved", "Approved", ("verified",))
    _upsert_property_status("active", "Active", ("available",))
    _upsert_property_status("rejected", "Rejected")
    _upsert_property_status("deal-closure-requested", "Deal Closure Requested")
    _upsert_property_status("deal-closed", "Deal Closed", ("deal_closed",))
    op.execute("UPDATE property_status SET is_active = false, updated_at = now() WHERE slug IN ('sold', 'rented')")


def downgrade() -> None:
    op.execute("UPDATE property_types SET is_active = true")
    op.drop_index("ix_agency_invitations_token", table_name="agency_invitations")
    op.drop_index("ix_agency_invitations_email_status", table_name="agency_invitations")
    op.drop_table("agency_invitations")
    op.drop_index("ix_agency_master_status", table_name="agency_master")
    op.drop_column("agency_master", "status")
