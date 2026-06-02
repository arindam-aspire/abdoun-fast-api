"""Extend features table with category/type taxonomy columns.

Revision ID: 0049_extend_features_taxonomy
Revises: 0048_add_owner_role
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_extend_features_taxonomy"
down_revision: Union[str, Sequence[str], None] = "0048_add_owner_role"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FEATURE_GROUP_DEFAULT = "FEATURE"


def upgrade() -> None:
    op.add_column(
        "features",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "features",
        sa.Column("property_type_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "features",
        sa.Column(
            "feature_group",
            sa.String(length=50),
            nullable=False,
            server_default=FEATURE_GROUP_DEFAULT,
        ),
    )
    op.add_column(
        "features",
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        sa.text(
            "UPDATE features SET feature_group = :fg WHERE feature_group IS NULL OR feature_group = ''"
        ).bindparams(fg=FEATURE_GROUP_DEFAULT)
    )

    op.create_foreign_key(
        "fk_features_category_id_property_categories",
        "features",
        "property_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_features_property_type_id_property_types",
        "features",
        "property_types",
        ["property_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_features_category_id", "features", ["category_id"])
    op.create_index("ix_features_property_type_id", "features", ["property_type_id"])
    op.create_index("ix_features_feature_group", "features", ["feature_group"])

    op.create_index(
        "uq_features_amenity_name_per_category",
        "features",
        ["category_id", "name"],
        unique=True,
        postgresql_where=sa.text(
            "feature_group = 'AMENITY' AND property_type_id IS NULL"
        ),
    )
    op.create_index(
        "uq_features_feature_name_per_category_type",
        "features",
        ["category_id", "property_type_id", "name"],
        unique=True,
        postgresql_where=sa.text(
            "feature_group = 'FEATURE' AND property_type_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_features_feature_name_per_category_type", table_name="features")
    op.drop_index("uq_features_amenity_name_per_category", table_name="features")
    op.drop_index("ix_features_feature_group", table_name="features")
    op.drop_index("ix_features_property_type_id", table_name="features")
    op.drop_index("ix_features_category_id", table_name="features")

    op.drop_constraint(
        "fk_features_property_type_id_property_types",
        "features",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_features_category_id_property_categories",
        "features",
        type_="foreignkey",
    )

    op.drop_column("features", "display_order")
    op.drop_column("features", "feature_group")
    op.drop_column("features", "property_type_id")
    op.drop_column("features", "category_id")
