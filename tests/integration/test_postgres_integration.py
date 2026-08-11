import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text, update
from sqlalchemy.exc import DBAPIError

from agent_control_plane.db_schema import audit_events
from agent_control_plane.models import (
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentSpec,
    AgentStatusUpdate,
    ApprovalDecision,
    ApprovalDecisionRequest,
    ApprovalRequestCreate,
    ApprovalStatus,
    RiskLevel,
)
from agent_control_plane.postgres_store import PostgresControlPlaneStore

pytestmark = pytest.mark.integration


def database_url() -> str:
    value = os.environ.get("ACP_DATABASE_URL")
    if not value:
        pytest.skip("ACP_DATABASE_URL is required for PostgreSQL integration tests")
    return value


def test_postgres_persists_governance_state_and_blocks_audit_mutation() -> None:
    url = database_url()
    agent_id = f"postgres-{uuid4().hex[:12]}"
    first_store = PostgresControlPlaneStore(url)
    assert first_store.is_ready() is True
    first_store.register_agent(
        AgentRegistrationRequest(
            spec=AgentSpec(
                agent_id=agent_id,
                version="1.0.0",
                display_name="PostgreSQL Agent",
                description="Verifies durable control-plane behavior.",
                entrypoint="https://agents.example.test/postgres",
            ),
            actor="operator@example.test",
        )
    )
    first_store.close()

    store = PostgresControlPlaneStore(url)
    assert store.get_agent(agent_id).revision == 1
    store.update_agent_status(
        agent_id,
        AgentStatusUpdate(
            status=AgentRuntimeStatus.ACTIVE,
            expected_revision=1,
            actor="operator@example.test",
            reason="Integration readiness passed.",
        ),
    )
    pending = store.create_approval(
        ApprovalRequestCreate(
            agent_id=agent_id,
            action="deployment.promote",
            risk=RiskLevel.HIGH,
            actor=agent_id,
            reason="Promotion requires approval.",
        )
    )
    approved = store.decide_approval(
        pending.request_id,
        ApprovalDecisionRequest(
            decision=ApprovalDecision.APPROVE,
            actor="reviewer@example.test",
            reason="Integration evidence passed.",
        ),
    )
    assert approved.status is ApprovalStatus.APPROVED
    assert len(store.list_audit_events(agent_id=agent_id)) == 4

    engine = create_engine(url)
    mutation_statements = (
        update(audit_events).values(summary="tampered"),
        delete(audit_events),
        text("TRUNCATE audit_events"),
    )
    for statement in mutation_statements:
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.execute(statement)
    engine.dispose()
    store.close()
