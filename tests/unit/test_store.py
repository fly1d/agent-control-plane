from datetime import UTC, datetime
from uuid import UUID

import pytest

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
from agent_control_plane.store import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    InMemoryControlPlaneStore,
    InvalidStatusTransitionError,
    RevisionConflictError,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def build_store() -> InMemoryControlPlaneStore:
    return InMemoryControlPlaneStore(clock=lambda: NOW)


def registration(agent_id: str = "support-agent") -> AgentRegistrationRequest:
    return AgentRegistrationRequest(
        spec=AgentSpec(
            agent_id=agent_id,
            version="1.0.0",
            display_name="Support Agent",
            description="Handles support requests with governed actions.",
            entrypoint="https://agents.example.test/support",
            capabilities=("ticket.read", "ticket.reply"),
        ),
        actor="operator@example.test",
    )


def register(store: InMemoryControlPlaneStore, agent_id: str = "support-agent") -> None:
    store.register_agent(registration(agent_id))


def approval_request(agent_id: str = "support-agent") -> ApprovalRequestCreate:
    return ApprovalRequestCreate(
        agent_id=agent_id,
        action="ticket.refund",
        risk=RiskLevel.HIGH,
        actor="support-agent",
        reason="Refund exceeds the automatic approval threshold.",
    )


def test_register_agent_creates_initial_state_and_audit_event() -> None:
    store = build_store()

    record = store.register_agent(registration())

    assert record.status is AgentRuntimeStatus.REGISTERED
    assert record.revision == 1
    assert record.registered_at == NOW
    assert store.get_agent("support-agent") == record
    event = store.list_audit_events()[0]
    assert event.event_type is AuditEventType.AGENT_REGISTERED
    assert event.actor == "operator@example.test"


def test_duplicate_agent_registration_is_rejected() -> None:
    store = build_store()
    register(store)

    with pytest.raises(AgentAlreadyExistsError):
        register(store)


def test_agents_are_listed_in_stable_id_order() -> None:
    store = build_store()
    register(store, "zeta-agent")
    register(store, "alpha-agent")

    records = store.list_agents()

    assert [record.spec.agent_id for record in records] == ["alpha-agent", "zeta-agent"]


def test_status_update_uses_optimistic_revision_and_creates_audit_event() -> None:
    store = build_store()
    register(store)

    updated = store.update_agent_status(
        "support-agent",
        AgentStatusUpdate(
            status=AgentRuntimeStatus.ACTIVE,
            expected_revision=1,
            actor="operator@example.test",
            reason="Production readiness checks passed.",
        ),
    )

    assert updated.status is AgentRuntimeStatus.ACTIVE
    assert updated.revision == 2
    assert store.list_audit_events()[0].event_type is AuditEventType.AGENT_STATUS_CHANGED


def test_stale_revision_and_invalid_transition_are_rejected() -> None:
    store = build_store()
    register(store)

    with pytest.raises(RevisionConflictError):
        store.update_agent_status(
            "support-agent",
            AgentStatusUpdate(
                status=AgentRuntimeStatus.ACTIVE,
                expected_revision=2,
                actor="operator@example.test",
                reason="Uses a stale copy.",
            ),
        )

    with pytest.raises(InvalidStatusTransitionError):
        store.update_agent_status(
            "support-agent",
            AgentStatusUpdate(
                status=AgentRuntimeStatus.REGISTERED,
                expected_revision=1,
                actor="operator@example.test",
                reason="No-op transitions are not allowed.",
            ),
        )


def test_approval_lifecycle_is_single_decision_and_audited() -> None:
    store = build_store()
    register(store)
    pending = store.create_approval(approval_request())

    approved = store.decide_approval(
        pending.request_id,
        ApprovalDecisionRequest(
            decision=ApprovalDecision.APPROVE,
            actor="reviewer@example.test",
            reason="Customer identity and refund evidence verified.",
        ),
    )

    assert approved.status is ApprovalStatus.APPROVED
    assert approved.decided_by == "reviewer@example.test"
    assert store.list_approvals(status=ApprovalStatus.PENDING) == ()
    assert [event.event_type for event in store.list_audit_events()] == [
        AuditEventType.APPROVAL_APPROVED,
        AuditEventType.APPROVAL_REQUESTED,
        AuditEventType.AGENT_REGISTERED,
    ]
    with pytest.raises(ApprovalAlreadyDecidedError):
        store.decide_approval(
            pending.request_id,
            ApprovalDecisionRequest(
                decision=ApprovalDecision.REJECT,
                actor="second-reviewer@example.test",
                reason="A second decision must not overwrite the first.",
            ),
        )


def test_approval_requires_a_registered_agent() -> None:
    store = build_store()

    with pytest.raises(AgentNotFoundError):
        store.create_approval(approval_request("missing-agent"))


def test_rejected_approval_is_audited_and_unknown_request_is_rejected() -> None:
    store = build_store()
    register(store)
    pending = store.create_approval(approval_request())

    rejected = store.decide_approval(
        pending.request_id,
        ApprovalDecisionRequest(
            decision=ApprovalDecision.REJECT,
            actor="reviewer@example.test",
            reason="Required evidence is missing.",
        ),
    )

    assert rejected.status is ApprovalStatus.REJECTED
    assert store.list_audit_events(limit=1)[0].event_type is AuditEventType.APPROVAL_REJECTED
    with pytest.raises(ApprovalNotFoundError):
        store.get_approval(UUID(int=0))
