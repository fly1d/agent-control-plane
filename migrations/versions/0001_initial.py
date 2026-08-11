"""Create the durable control-plane system of record.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("agent_id", sa.String(length=63), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_agents_positive_revision")),
        sa.CheckConstraint(
            "status IN ('registered', 'active', 'paused')",
            name=op.f("ck_agents_valid_status"),
        ),
        sa.PrimaryKeyConstraint("agent_id", name=op.f("pk_agents")),
    )
    op.create_table(
        "approval_requests",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=63), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("risk", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("request_reason", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "(status = 'pending' AND decided_at IS NULL AND decided_by IS NULL "
            "AND decision_reason IS NULL) OR "
            "(status IN ('approved', 'rejected') AND decided_at IS NOT NULL "
            "AND decided_by IS NOT NULL AND decision_reason IS NOT NULL)",
            name=op.f("ck_approval_requests_decision_consistency"),
        ),
        sa.CheckConstraint(
            "risk IN ('low', 'medium', 'high')",
            name=op.f("ck_approval_requests_valid_risk"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_approval_requests_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.agent_id"],
            name=op.f("fk_approval_requests_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("request_id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        op.f("ix_approval_requests_agent"),
        "approval_requests",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_queue"),
        "approval_requests",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "audit_events",
        sa.Column("sequence", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(length=63), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('agent.registered', 'agent.status_changed', "
            "'approval.requested', 'approval.approved', 'approval.rejected')",
            name=op.f("ck_audit_events_valid_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.agent_id"],
            name=op.f("fk_audit_events_agent_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("sequence", name=op.f("pk_audit_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_audit_events_event_id")),
    )
    op.create_index(
        op.f("ix_audit_events_agent_sequence"),
        "audit_events",
        ["agent_id", "sequence"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_event_mutation()")
    op.drop_index("ix_audit_events_agent_sequence", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_approval_requests_queue", table_name="approval_requests")
    op.drop_index("ix_approval_requests_agent", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_table("agents")
