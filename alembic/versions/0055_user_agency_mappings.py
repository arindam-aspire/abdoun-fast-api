"""add user agency mappings and submission agency scope

Revision ID: 0055_user_agency_mappings
Revises: 0054_property_deal_closures
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0055_user_agency_mappings"
down_revision = "0054_property_deal_closures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_agency_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agency_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agency_master.id"), nullable=False),
        sa.Column("relationship_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_agency_mappings_user_status", "user_agency_mappings", ["user_id", "status"])
    op.create_index("ix_user_agency_mappings_agency_type_status", "user_agency_mappings", ["agency_id", "relationship_type", "status"])
    op.create_index(
        "uq_user_agency_mappings_active_pair",
        "user_agency_mappings",
        ["user_id", "agency_id", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_user_agency_mappings_single_agency_roles",
        "user_agency_mappings",
        ["user_id", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'active' AND relationship_type IN ('agency_admin', 'agency_owner', 'agent')"),
    )

    op.add_column("property_listing_submissions", sa.Column("agency_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_property_listing_submissions_agency_id",
        "property_listing_submissions",
        "agency_master",
        ["agency_id"],
        ["id"],
    )
    op.create_index("ix_property_listing_submissions_agency_status", "property_listing_submissions", ["agency_id", "status"])
    op.create_index("ix_property_listing_submissions_agency_property", "property_listing_submissions", ["agency_id", "property_id"])

    op.execute(
        """
        INSERT INTO user_agency_mappings (user_id, agency_id, relationship_type, status, is_primary, created_at, updated_at)
        SELECT DISTINCT
            u.id,
            u.agency_id,
            CASE
                WHEN r.name = 'admin' THEN 'agency_admin'
                WHEN r.name = 'agent' THEN 'agent'
                WHEN r.name = 'owner' THEN 'property_owner'
                ELSE 'property_owner'
            END AS relationship_type,
            'active',
            true,
            now(),
            now()
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE u.agency_id IS NOT NULL
          AND r.name IN ('admin', 'agent', 'owner', 'registered_user')
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        UPDATE property_listing_submissions pls
        SET agency_id = u.agency_id
        FROM users u
        WHERE u.id = pls.submitted_by
          AND pls.agency_id IS NULL
          AND u.agency_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_property_listing_submissions_agency_property", table_name="property_listing_submissions")
    op.drop_index("ix_property_listing_submissions_agency_status", table_name="property_listing_submissions")
    op.drop_constraint("fk_property_listing_submissions_agency_id", "property_listing_submissions", type_="foreignkey")
    op.drop_column("property_listing_submissions", "agency_id")

    op.drop_index("uq_user_agency_mappings_single_agency_roles", table_name="user_agency_mappings")
    op.drop_index("uq_user_agency_mappings_active_pair", table_name="user_agency_mappings")
    op.drop_index("ix_user_agency_mappings_agency_type_status", table_name="user_agency_mappings")
    op.drop_index("ix_user_agency_mappings_user_status", table_name="user_agency_mappings")
    op.drop_table("user_agency_mappings")
