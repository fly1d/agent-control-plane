from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from agent_control_plane.db_schema import REQUIRED_SCHEMA_REVISION, metadata
from agent_control_plane.models import (
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentSpec,
    AgentStatusUpdate,
    ApprovalDecision,
    ApprovalDecisionRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    AuditEventType,
    RiskLevel,
)
from agent_control_plane.postgres_store import PostgresControlPlaneStore
from agent_control_plane.store import (
    AgentAlreadyExistsError,
    AgentNotActiveError,
    AgentNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    InvalidStatusTransitionError,
    RevisionConflictError,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def build_store() -> PostgresControlPlaneStore:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    stamp_test_schema(engine)
    return PostgresControlPlaneStore(engine=engine, clock=lambda: NOW)


def stamp_test_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": REQUIRED_SCHEMA_REVISION},
        )


def registration(agent_id: str = "sql-agent") -> AgentRegistrationRequest:
    return AgentRegistrationRequest(
        spec=AgentSpec(
            agent_id=agent_id,
            version="1.0.0",
            display_name="SQL Agent",
            description="Exercises the transactional store.",
            entrypoint="https://agents.example.test/sql",
            capabilities=("ticket.read", "ticket.reply"),
        ),
        actor="operator@example.test",
    )


def status_update(status: AgentRuntimeStatus, expected_revision: int = 1) -> AgentStatusUpdate:
    return AgentStatusUpdate(
        status=status,
        expected_revision=expected_revision,
        actor="operator@example.test",
        reason="Exercise status transitions.",
    )


def approval_request(agent_id: str = "sql-agent") -> ApprovalRequestCreate:
    return ApprovalRequestCreate(
        agent_id=agent_id,
        action="ticket.refund",
        risk=RiskLevel.HIGH,
        actor=agent_id,
        reason="Refund requires review.",
    )


def test_constructor_requires_exactly_one_connection_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        PostgresControlPlaneStore()

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with pytest.raises(ValueError, match="exactly one"):
        PostgresControlPlaneStore("sqlite+pysqlite:///:memory:", engine=engine)
    engine.dispose()


def test_constructor_uses_psycopg_for_a_bare_postgres_url() -> None:
    store = PostgresControlPlaneStore("postgresql://user:password@localhost/database")

    assert store._engine.url.drivername == "postgresql+psycopg"
    store.close()


def test_readiness_tracks_required_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    store = PostgresControlPlaneStore(engine=engine)
    assert store.is_ready() is False

    metadata.create_all(engine)
    assert store.is_ready() is False
    stamp_test_schema(engine)
    assert store.is_ready() is True
    store.close()


def test_agent_lifecycle_is_persisted_and_conflicts_fail_closed() -> None:
    store = build_store()
    registered = store.register_agent(registration())

    assert registered.status is AgentRuntimeStatus.REGISTERED
    assert store.get_agent("sql-agent") == registered
    assert [item.spec.agent_id for item in store.list_agents()] == ["sql-agent"]
    with pytest.raises(AgentAlreadyExistsError):
        store.register_agent(registration())
    with pytest.raises(AgentNotFoundError):
        store.get_agent("missing-agent")
    with pytest.raises(RevisionConflictError):
        store.update_agent_status("sql-agent", status_update(AgentRuntimeStatus.ACTIVE, 2))
    with pytest.raises(InvalidStatusTransitionError):
        store.update_agent_status("sql-agent", status_update(AgentRuntimeStatus.REGISTERED))

    active = store.update_agent_status("sql-agent", status_update(AgentRuntimeStatus.ACTIVE))
    assert active.revision == 2
    assert active.status is AgentRuntimeStatus.ACTIVE
    store.close()


def test_approval_lifecycle_is_transactional_and_filterable() -> None:
    store = build_store()
    store.register_agent(registration())
    with pytest.raises(AgentNotActiveError):
        store.create_approval(approval_request())
    with pytest.raises(AgentNotFoundError):
        store.create_approval(approval_request("missing-agent"))
    store.update_agent_status("sql-agent", status_update(AgentRuntimeStatus.ACTIVE))

    pending = store.create_approval(approval_request())
    assert store.get_approval(pending.request_id) == pending
    assert store.list_approvals(status=ApprovalStatus.PENDING) == (pending,)
    assert store.list_approvals(agent_id="missing-agent") == ()

    approved = store.decide_approval(
        pending.request_id,
        ApprovalDecisionRequest(
            decision=ApprovalDecision.APPROVE,
            actor="reviewer@example.test",
            reason="Evidence verified.",
        ),
    )
    assert approved.status is ApprovalStatus.APPROVED
    with pytest.raises(ApprovalAlreadyDecidedError):
        store.decide_approval(
            pending.request_id,
            ApprovalDecisionRequest(
                decision=ApprovalDecision.REJECT,
                actor="reviewer@example.test",
                reason="A second decision is forbidden.",
            ),
        )
    with pytest.raises(ApprovalNotFoundError):
        store.get_approval(UUID(int=0))
    with pytest.raises(ApprovalNotFoundError):
        store.decide_approval(
            UUID(int=0),
            ApprovalDecisionRequest(
                decision=ApprovalDecision.REJECT,
                actor="reviewer@example.test",
                reason="Unknown request.",
            ),
        )

    events = store.list_audit_events(agent_id="sql-agent", limit=2)
    assert [event.event_type for event in events] == [
        AuditEventType.APPROVAL_APPROVED,
        AuditEventType.APPROVAL_REQUESTED,
    ]
    store.close()


def test_rejection_path_is_persisted() -> None:
    store = build_store()
    store.register_agent(registration())
    store.update_agent_status("sql-agent", status_update(AgentRuntimeStatus.ACTIVE))
    pending = store.create_approval(approval_request())

    rejected = store.decide_approval(
        pending.request_id,
        ApprovalDecisionRequest(
            decision=ApprovalDecision.REJECT,
            actor="reviewer@example.test",
            reason="Evidence missing.",
        ),
    )

    assert rejected.status is ApprovalStatus.REJECTED
    assert store.list_audit_events(limit=1)[0].event_type is AuditEventType.APPROVAL_REJECTED
    store.close()
