"""Store the licence URL selected with an agency invitation.

Revision ID: 0078_agency_invitation_document
Revises: 0077_prefixed_property_refs
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0078_agency_invitation_document"
down_revision = "0077_prefixed_property_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agency_invitations",
        sa.Column("legal_document_s3_link", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agency_invitations", "legal_document_s3_link")
