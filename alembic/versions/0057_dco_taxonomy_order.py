"""add dco taxonomy display order

Revision ID: 0057_dco_taxonomy_order
Revises: 0056_dco_taxonomy_workflows
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0057_dco_taxonomy_order"
down_revision = "0056_dco_taxonomy_workflows"
branch_labels = None
depends_on = None


def _set_category_order(slug: str, order: int) -> None:
    op.execute(
        sa.text("UPDATE property_categories SET display_order = :order WHERE slug = :slug").bindparams(
            order=order,
            slug=slug,
        )
    )


def _set_type_order(category_slug: str, type_slug: str, order: int) -> None:
    op.execute(
        sa.text(
            """
            UPDATE property_types pt
            SET display_order = :order
            FROM property_categories pc
            WHERE pc.id = pt.category_id
              AND pc.slug = :category_slug
              AND pt.slug = :type_slug
            """
        ).bindparams(order=order, category_slug=category_slug, type_slug=type_slug)
    )


def _set_status_order(slug: str, order: int) -> None:
    op.execute(
        sa.text("UPDATE property_status SET display_order = :order WHERE slug = :slug").bindparams(
            order=order,
            slug=slug,
        )
    )


def upgrade() -> None:
    op.add_column("property_categories", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("property_types", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("property_status", sa.Column("display_order", sa.Integer(), nullable=True))

    for order, slug in enumerate(("residential", "commercial", "land"), start=1):
        _set_category_order(slug, order)

    taxonomy = {
        "residential": ("apartments", "villas", "buildings", "farms"),
        "commercial": ("offices", "showrooms", "buildings", "warehouse", "businesses", "villas"),
        "land": (
            "residential-lands",
            "commercial-lands",
            "industrial-lands",
            "agricultural-lands",
            "mixed-use-lands",
        ),
    }
    for category_slug, type_slugs in taxonomy.items():
        for order, type_slug in enumerate(type_slugs, start=1):
            _set_type_order(category_slug, type_slug, order)

    status_slugs = (
        "draft",
        "pending-approval",
        "active",
        "rejected",
        "deal-closure-requested",
        "deal-closed",
    )
    for order, slug in enumerate(status_slugs, start=1):
        _set_status_order(slug, order)


def downgrade() -> None:
    op.drop_column("property_status", "display_order")
    op.drop_column("property_types", "display_order")
    op.drop_column("property_categories", "display_order")
