"""add integer id and move url to separate column

Revision ID: 0002_add_integer_id
Revises: 0001_create_properties
Create Date: 2026-02-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_integer_id"
down_revision = "0001_create_properties"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add new url column and copy existing id (URL) to it
    op.add_column("properties", sa.Column("url", sa.String(), nullable=True))
    op.execute("UPDATE properties SET url = id")
    
    # Step 2: Create sequence for integer IDs
    op.execute("CREATE SEQUENCE IF NOT EXISTS properties_id_seq")
    
    # Step 3: Add new integer id column (temporarily nullable)
    op.add_column("properties", sa.Column("id_new", sa.Integer(), nullable=True))
    
    # Step 4: Populate id_new with sequential numbers for existing rows
    # For simplicity, we'll use a loop in a DO block
    op.execute("""
        DO $$
        DECLARE
            r RECORD;
            counter INTEGER := 1;
        BEGIN
            FOR r IN SELECT ctid FROM properties ORDER BY created_at
            LOOP
                UPDATE properties SET id_new = counter WHERE ctid = r.ctid;
                counter := counter + 1;
            END LOOP;
        END $$;
    """)
    
    # Step 5: Set sequence to continue from max id_new
    op.execute("""
        SELECT setval('properties_id_seq', COALESCE((SELECT MAX(id_new) FROM properties), 1), true)
    """)
    
    # Step 6: Make id_new NOT NULL and set default
    op.alter_column("properties", "id_new", nullable=False, server_default=sa.text("nextval('properties_id_seq')"))
    
    # Step 7: Drop old primary key constraint
    op.drop_constraint("properties_pkey", "properties", type_="primary")
    
    # Step 8: Drop old id column
    op.drop_column("properties", "id")
    
    # Step 9: Rename id_new to id
    op.alter_column("properties", "id_new", new_column_name="id")
    
    # Step 10: Set id as primary key
    op.create_primary_key("properties_pkey", "properties", ["id"])
    
    # Step 11: Add unique constraint and index on url
    op.create_unique_constraint("uq_properties_url", "properties", ["url"])
    op.create_index("idx_properties_url", "properties", ["url"])


def downgrade() -> None:
    # Remove index and constraint on url
    op.drop_index("idx_properties_url", table_name="properties")
    op.drop_constraint("uq_properties_url", "properties", type_="unique")
    
    # Drop primary key
    op.drop_constraint("properties_pkey", "properties", type_="primary")
    
    # Add back old id column (string)
    op.add_column("properties", sa.Column("id_old", sa.String(), nullable=True))
    
    # Copy url back to id_old
    op.execute("UPDATE properties SET id_old = url")
    
    # Drop new id column
    op.drop_column("properties", "id")
    
    # Rename id_old to id
    op.alter_column("properties", "id_old", new_column_name="id", nullable=False)
    
    # Set id as primary key
    op.create_primary_key("properties_pkey", "properties", ["id"])
    
    # Drop url column
    op.drop_column("properties", "url")
    
    # Drop sequence
    op.execute("DROP SEQUENCE IF EXISTS properties_id_seq")

