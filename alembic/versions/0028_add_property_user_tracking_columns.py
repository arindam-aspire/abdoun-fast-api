"""add property user tracking columns, dashboard entities, and analytics indexes

Revision ID: 0028_property_user_tracking
Revises: 0027_recently_viewed_properties
Create Date: 2026-04-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0028_property_user_tracking"
down_revision: Union[str, None] = "0027_recently_viewed_properties"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

property_view_user_type = sa.Enum(
    "guest",
    "registered",
    name="property_view_user_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "properties_normalized",
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("agent_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "properties_normalized",
        sa.Column("deal_closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_foreign_key(
        "fk_properties_created_by_user",
        "properties_normalized",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_properties_updated_by_user",
        "properties_normalized",
        "users",
        ["updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_properties_agent_user",
        "properties_normalized",
        "users",
        ["agent_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_properties_approved_by_user",
        "properties_normalized",
        "users",
        ["approved_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_properties_created_by_user_id",
        "properties_normalized",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_properties_updated_by_user_id",
        "properties_normalized",
        ["updated_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_properties_agent_user_id",
        "properties_normalized",
        ["agent_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_properties_approved_by_user_id",
        "properties_normalized",
        ["approved_by_user_id"],
        unique=False,
    )

    property_view_user_type.create(bind, checkfirst=True)

    property_view_user_type_db = postgresql.ENUM(
        "guest",
        "registered",
        name="property_view_user_type",
        create_type=False,
    )

    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inquiry_type", sa.String(length=50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties_normalized.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "property_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_type", property_view_user_type_db, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties_normalized.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_type", sa.String(length=50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("tone", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["property_id"], ["properties_normalized.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "dashboard_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_properties", sa.Integer(), nullable=True),
        sa.Column("active_properties", sa.Integer(), nullable=True),
        sa.Column("draft_properties", sa.Integer(), nullable=True),
        sa.Column("total_views", sa.Integer(), nullable=True),
        sa.Column("total_inquiries", sa.Integer(), nullable=True),
        sa.Column("total_deals", sa.Integer(), nullable=True),
        sa.Column("conversion_rate", sa.Numeric(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        INSERT INTO property_status (name, slug, is_active)
        SELECT 'Deal Closed', 'deal_closed', true
        WHERE NOT EXISTS (
            SELECT 1 FROM property_status WHERE slug = 'deal_closed'
        )
        """
    )

    # Analytics / dashboard query paths
    op.create_index("ix_leads_property_id", "leads", ["property_id"], unique=False)
    op.create_index("ix_leads_created_at", "leads", ["created_at"], unique=False)
    op.create_index("ix_property_views_property_id", "property_views", ["property_id"], unique=False)
    op.create_index("ix_property_views_viewed_at", "property_views", ["viewed_at"], unique=False)
    op.create_index("ix_activity_logs_user_id", "activity_logs", ["user_id"], unique=False)
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"], unique=False)
    op.create_index("ix_dashboard_summary_user_id", "dashboard_summary", ["user_id"], unique=False)
    op.create_index("ix_dashboard_summary_last_updated", "dashboard_summary", ["last_updated"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM property_status WHERE slug = 'deal_closed'")
    bind = op.get_bind()

    op.drop_index("ix_dashboard_summary_last_updated", table_name="dashboard_summary")
    op.drop_index("ix_dashboard_summary_user_id", table_name="dashboard_summary")
    op.drop_index("ix_activity_logs_created_at", table_name="activity_logs")
    op.drop_index("ix_activity_logs_user_id", table_name="activity_logs")
    op.drop_index("ix_property_views_viewed_at", table_name="property_views")
    op.drop_index("ix_property_views_property_id", table_name="property_views")
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_index("ix_leads_property_id", table_name="leads")

    op.drop_table("dashboard_summary")
    op.drop_table("activity_logs")
    op.drop_table("property_views")
    op.drop_table("leads")

    property_view_user_type.drop(bind, checkfirst=True)

    op.drop_column("properties_normalized", "deal_closed")

    op.drop_index("ix_properties_approved_by_user_id", table_name="properties_normalized")
    op.drop_index("ix_properties_agent_user_id", table_name="properties_normalized")
    op.drop_index("ix_properties_updated_by_user_id", table_name="properties_normalized")
    op.drop_index("ix_properties_created_by_user_id", table_name="properties_normalized")

    op.drop_constraint(
        "fk_properties_approved_by_user",
        "properties_normalized",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_properties_agent_user",
        "properties_normalized",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_properties_updated_by_user",
        "properties_normalized",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_properties_created_by_user",
        "properties_normalized",
        type_="foreignkey",
    )

    op.drop_column("properties_normalized", "approved_by_user_id")
    op.drop_column("properties_normalized", "agent_user_id")
    op.drop_column("properties_normalized", "updated_by_user_id")
    op.drop_column("properties_normalized", "created_by_user_id")
