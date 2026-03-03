"""add property_translations table for i18n (title, description per language)

Revision ID: 0007_property_translations
Revises: 0006_more_features
Create Date: 2026-02-26

Best practice: separate translation table, not JSONB.
- title and description translated; slug is derived from title when needed.
- UNIQUE(property_id, language_code).
- Index (property_id, language_code) for fast lookups.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_property_translations"
down_revision = "0006_more_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_translations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties_normalized.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language_code", sa.String(5), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("property_id", "language_code", name="uq_property_translations_property_lang"),
    )
    op.create_index(
        "idx_property_translations_property_lang",
        "property_translations",
        ["property_id", "language_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_property_translations_property_lang", table_name="property_translations")
    op.drop_table("property_translations")
