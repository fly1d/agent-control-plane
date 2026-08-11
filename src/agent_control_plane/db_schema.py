"""SQLAlchemy Core schema shared by the PostgreSQL adapter and migration tooling."""

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
)
from sqlalchemy.dialects import postgresql

REQUIRED_SCHEMA_REVISION = "0001_initial"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
specification_type = JSON().with_variant(postgresql.JSONB(), "postgresql")

agents = Table(
    "agents",
    metadata,
    Column("agent_id", String(63), primary_key=True),
    Column("spec", specification_type, nullable=False),
    Column("status", String(20), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("revision >= 1", name="positive_revision"),
    CheckConstraint("status IN ('registered', 'active', 'paused')", name="valid_status"),
)

approval_requests = Table(
    "approval_requests",
    metadata,
    Column("request_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "agent_id",
        String(63),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("action", String(128), nullable=False),
    Column("risk", String(20), nullable=False),
    Column("status", String(20), nullable=False),
    Column("requested_by", String(128), nullable=False),
    Column("request_reason", String(500), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("decided_by", String(128)),
    Column("decision_reason", String(500)),
    CheckConstraint("risk IN ('low', 'medium', 'high')", name="valid_risk"),
    CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="valid_status"),
    CheckConstraint(
        "(status = 'pending' AND decided_at IS NULL AND decided_by IS NULL "
        "AND decision_reason IS NULL) OR "
        "(status IN ('approved', 'rejected') AND decided_at IS NOT NULL "
        "AND decided_by IS NOT NULL AND decision_reason IS NOT NULL)",
        name="decision_consistency",
    ),
)
Index("ix_approval_requests_queue", approval_requests.c.status, approval_requests.c.created_at)
Index("ix_approval_requests_agent", approval_requests.c.agent_id)

audit_sequence_type = BigInteger().with_variant(Integer, "sqlite")
audit_events = Table(
    "audit_events",
    metadata,
    Column("sequence", audit_sequence_type, Identity(), primary_key=True),
    Column("event_id", Uuid(as_uuid=True), nullable=False, unique=True),
    Column(
        "agent_id",
        String(63),
        ForeignKey("agents.agent_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("event_type", String(40), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("resource_id", String(128), nullable=False),
    Column("summary", String(1000), nullable=False),
    CheckConstraint(
        "event_type IN ('agent.registered', 'agent.status_changed', "
        "'approval.requested', 'approval.approved', 'approval.rejected')",
        name="valid_event_type",
    ),
)
Index("ix_audit_events_agent_sequence", audit_events.c.agent_id, audit_events.c.sequence)
