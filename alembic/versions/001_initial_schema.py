"""Initial migration for Agentic Development Platform."""
from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create the base tables for the agentic platform.

    Tables:
      - task: immutable tasks with status, priority, and hierarchy.
      - session: active development sessions and their event stream.
    """

    # Task table
    op.create_table(
        "task",
        sa.Column("task_id", sa.String(), nullable=False, primary_key=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            default="pending",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            default=5,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.Column("parent_id", sa.String(), nullable=True),  # self‑referencing parent
        sa.Column("depends_on", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )

    # Indexes for task
    op.create_index("ix_task_project_id", "task", ["project_id"])
    op.create_index("ix_task_status", "task", ["status"])
    op.create_index("ix_task_priority", "task", ["priority"])
    op.create_index("ix_task_parent_id", "task", ["parent_id"])


    # Session table
    op.create_table(
        "session",
        sa.Column("session_id", sa.String(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.Column("active_agent_id", sa.String(), nullable=True),
        sa.Column("task_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("events", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )

    # Indexes for session
    op.create_index("ix_session_user_id", "session", ["user_id"])
    op.create_index("ix_session_project_id", "session", ["project_id"])
    op.create_index("ix_session_status", "session", ["status"])


def downgrade() -> None:
    """
    Drop all tables created in this revision.
    """
    op.drop_table("session")
    op.drop_table("task")
