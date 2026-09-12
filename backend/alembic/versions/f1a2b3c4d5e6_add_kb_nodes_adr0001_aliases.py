"""add_kb_nodes_adr0001_aliases

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-12 13:45:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Добавление полей-алиасов в kb_documents
    op.execute(
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS id VARCHAR(64) GENERATED ALWAYS AS (doc_id) STORED;"
    )
    op.execute(
        "ALTER TABLE kb_documents ADD COLUMN IF NOT EXISTS source_type VARCHAR(32) DEFAULT 'regulation';"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kb_documents_id ON kb_documents(id);"
    )

    # Добавление полей-алиасов в kb_nodes (ADR-0001)
    op.execute(
        "ALTER TABLE kb_nodes ADD COLUMN IF NOT EXISTS id VARCHAR(64) GENERATED ALWAYS AS (node_id) STORED;"
    )
    op.execute(
        "ALTER TABLE kb_nodes ADD COLUMN IF NOT EXISTS document_id VARCHAR(64) GENERATED ALWAYS AS (doc_id) STORED;"
    )
    op.execute(
        "ALTER TABLE kb_nodes ADD COLUMN IF NOT EXISTS parent_id VARCHAR(64) GENERATED ALWAYS AS (parent_node_id) STORED;"
    )
    op.execute(
        "ALTER TABLE kb_nodes ADD COLUMN IF NOT EXISTS content_markdown TEXT GENERATED ALWAYS AS (full_content) STORED;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_kb_nodes_id ON kb_nodes(id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_kb_nodes_id;")
    op.execute("ALTER TABLE kb_nodes DROP COLUMN IF EXISTS content_markdown;")
    op.execute("ALTER TABLE kb_nodes DROP COLUMN IF EXISTS parent_id;")
    op.execute("ALTER TABLE kb_nodes DROP COLUMN IF EXISTS document_id;")
    op.execute("ALTER TABLE kb_nodes DROP COLUMN IF EXISTS id;")

    op.execute("DROP INDEX IF EXISTS idx_kb_documents_id;")
    op.execute("ALTER TABLE kb_documents DROP COLUMN IF EXISTS source_type;")
    op.execute("ALTER TABLE kb_documents DROP COLUMN IF EXISTS id;")
