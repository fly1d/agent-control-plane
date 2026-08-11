"""Storage boundary and the development in-memory control-plane adapter."""

from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from agent_control_plane.models import (
    AgentRecord,
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentStatusUpdate,
    ApprovalDecision,
    ApprovalDecisionRequest,
    ApprovalRecord,
    ApprovalRequestCreate,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
)


class StoreError(Exception):
    """Base error for expected control-plane storage failures."""


class AgentAlreadyExistsError(StoreError):
    pass


class AgentNotFoundError(StoreError):
    pass


class AgentNotActiveError(StoreError):
    pass


class RevisionConflictError(StoreError):
    pass


class InvalidStatusTransitionError(StoreError):
    pass


class ApprovalNotFoundError(StoreError):
    pass


class ApprovalAlreadyDecidedError(StoreError):
    pass


class ControlPlaneStore(Protocol):
    def is_ready(self) -> bool: ...

    def close(self) -> None: ...

    def register_agent(self, request: AgentRegistrationRequest) -> AgentRecord: ...

    def get_agent(self, agent_id: str) -> AgentRecord: ...

    def list_agents(self) -> tuple[AgentRecord, ...]: ...

    def update_agent_status(self, agent_id: str, update: AgentStatusUpdate) -> AgentRecord: ...

    def create_approval(self, request: ApprovalRequestCreate) -> ApprovalRecord: ...

    def get_approval(self, request_id: UUID) -> ApprovalRecord: ...

    def list_approvals(
        self, status: ApprovalStatus | None = None, agent_id: str | None = None
    ) -> tuple[ApprovalRecord, ...]: ...

    def decide_approval(
        self, request_id: UUID, decision: ApprovalDecisionRequest
    ) -> ApprovalRecord: ...

    def list_audit_events(
        self, agent_id: str | None = None, limit: int = 100
    ) -> tuple[AuditEvent, ...]: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


ALLOWED_STATUS_TRANSITIONS = {
    AgentRuntimeStatus.REGISTERED: {AgentRuntimeStatus.ACTIVE, AgentRuntimeStatus.PAUSED},
    AgentRuntimeStatus.ACTIVE: {AgentRuntimeStatus.PAUSED},
    AgentRuntimeStatus.PAUSED: {AgentRuntimeStatus.ACTIVE},
}


def validate_status_transition(current: AgentRuntimeStatus, requested: AgentRuntimeStatus) -> None:
    if requested not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise InvalidStatusTransitionError(
            f"cannot change agent status from '{current}' to '{requested}'"
        )


def validate_agent_is_active(record: AgentRecord) -> None:
    if record.status is not AgentRuntimeStatus.ACTIVE:
        raise AgentNotActiveError(
            f"agent '{record.spec.agent_id}' must be active to request approval"
        )


class InMemoryControlPlaneStore:
    """Concurrency-safe adapter for development and single-process evaluation."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory
        self._agents: dict[str, AgentRecord] = {}
        self._approvals: dict[UUID, ApprovalRecord] = {}
        self._audit_events: list[AuditEvent] = []
        self._lock = RLock()

    def is_ready(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def register_agent(self, request: AgentRegistrationRequest) -> AgentRecord:
        with self._lock:
            agent_id = request.spec.agent_id
            if agent_id in self._agents:
                raise AgentAlreadyExistsError(f"agent '{agent_id}' is already registered")

            timestamp = self._clock()
            record = AgentRecord(
                spec=request.spec,
                status=AgentRuntimeStatus.REGISTERED,
                revision=1,
                registered_at=timestamp,
                updated_at=timestamp,
            )
            self._agents[agent_id] = record
            self._append_event(
                event_type=AuditEventType.AGENT_REGISTERED,
                agent_id=agent_id,
                actor=request.actor,
                occurred_at=timestamp,
                resource_id=agent_id,
                summary=f"Registered agent version {request.spec.version}",
            )
            return record

    def get_agent(self, agent_id: str) -> AgentRecord:
        with self._lock:
            try:
                return self._agents[agent_id]
            except KeyError as error:
                raise AgentNotFoundError(f"agent '{agent_id}' was not found") from error

    def list_agents(self) -> tuple[AgentRecord, ...]:
        with self._lock:
            return tuple(self._agents[agent_id] for agent_id in sorted(self._agents))

    def update_agent_status(self, agent_id: str, update: AgentStatusUpdate) -> AgentRecord:
        with self._lock:
            current = self.get_agent(agent_id)
            if current.revision != update.expected_revision:
                raise RevisionConflictError(
                    f"expected revision {update.expected_revision}, current revision is "
                    f"{current.revision}"
                )
            validate_status_transition(current.status, update.status)

            timestamp = self._clock()
            updated = current.model_copy(
                update={
                    "status": update.status,
                    "revision": current.revision + 1,
                    "updated_at": timestamp,
                }
            )
            self._agents[agent_id] = updated
            self._append_event(
                event_type=AuditEventType.AGENT_STATUS_CHANGED,
                agent_id=agent_id,
                actor=update.actor,
                occurred_at=timestamp,
                resource_id=agent_id,
                summary=f"Changed status from {current.status} to {update.status}: {update.reason}",
            )
            return updated

    def create_approval(self, request: ApprovalRequestCreate) -> ApprovalRecord:
        with self._lock:
            agent = self.get_agent(request.agent_id)
            validate_agent_is_active(agent)
            timestamp = self._clock()
            request_id = self._id_factory()
            record = ApprovalRecord(
                request_id=request_id,
                agent_id=request.agent_id,
                action=request.action,
                risk=request.risk,
                status=ApprovalStatus.PENDING,
                requested_by=request.actor,
                request_reason=request.reason,
                created_at=timestamp,
            )
            self._approvals[request_id] = record
            self._append_event(
                event_type=AuditEventType.APPROVAL_REQUESTED,
                agent_id=request.agent_id,
                actor=request.actor,
                occurred_at=timestamp,
                resource_id=str(request_id),
                summary=f"Requested {request.risk} approval for {request.action}",
            )
            return record

    def get_approval(self, request_id: UUID) -> ApprovalRecord:
        with self._lock:
            try:
                return self._approvals[request_id]
            except KeyError as error:
                raise ApprovalNotFoundError(
                    f"approval request '{request_id}' was not found"
                ) from error

    def list_approvals(
        self, status: ApprovalStatus | None = None, agent_id: str | None = None
    ) -> tuple[ApprovalRecord, ...]:
        with self._lock:
            records = (
                record
                for record in self._approvals.values()
                if (status is None or record.status == status)
                and (agent_id is None or record.agent_id == agent_id)
            )
            return tuple(
                sorted(records, key=lambda record: (record.created_at, str(record.request_id)))
            )

    def decide_approval(
        self, request_id: UUID, decision: ApprovalDecisionRequest
    ) -> ApprovalRecord:
        with self._lock:
            current = self.get_approval(request_id)
            if current.status is not ApprovalStatus.PENDING:
                raise ApprovalAlreadyDecidedError(
                    f"approval request '{request_id}' has already been decided"
                )

            timestamp = self._clock()
            status = (
                ApprovalStatus.APPROVED
                if decision.decision is ApprovalDecision.APPROVE
                else ApprovalStatus.REJECTED
            )
            updated = current.model_copy(
                update={
                    "status": status,
                    "decided_at": timestamp,
                    "decided_by": decision.actor,
                    "decision_reason": decision.reason,
                }
            )
            self._approvals[request_id] = updated
            self._append_event(
                event_type=(
                    AuditEventType.APPROVAL_APPROVED
                    if status is ApprovalStatus.APPROVED
                    else AuditEventType.APPROVAL_REJECTED
                ),
                agent_id=current.agent_id,
                actor=decision.actor,
                occurred_at=timestamp,
                resource_id=str(request_id),
                summary=f"{status.value.capitalize()} {current.action}: {decision.reason}",
            )
            return updated

    def list_audit_events(
        self, agent_id: str | None = None, limit: int = 100
    ) -> tuple[AuditEvent, ...]:
        with self._lock:
            matching = (
                event
                for event in reversed(self._audit_events)
                if agent_id is None or event.agent_id == agent_id
            )
            return tuple(event for _, event in zip(range(limit), matching, strict=False))

    def _append_event(
        self,
        *,
        event_type: AuditEventType,
        agent_id: str,
        actor: str,
        occurred_at: datetime,
        resource_id: str,
        summary: str,
    ) -> None:
        self._audit_events.append(
            AuditEvent(
                event_id=self._id_factory(),
                event_type=event_type,
                agent_id=agent_id,
                actor=actor,
                occurred_at=occurred_at,
                resource_id=resource_id,
                summary=summary,
            )
        )
