"""Transactional SQL store used with PostgreSQL in durable deployments."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import overload
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, insert, inspect, select, text, update
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from agent_control_plane.db_schema import (
    REQUIRED_SCHEMA_REVISION,
    agents,
    approval_requests,
    audit_events,
)
from agent_control_plane.models import (
    AgentRecord,
    AgentRegistrationRequest,
    AgentRuntimeStatus,
    AgentSpec,
    AgentStatusUpdate,
    ApprovalDecision,
    ApprovalDecisionRequest,
    ApprovalRecord,
    ApprovalRequestCreate,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
)
from agent_control_plane.store import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    RevisionConflictError,
    utc_now,
    validate_agent_is_active,
    validate_status_transition,
)


class PostgresControlPlaneStore:
    """Persist control-plane state and audit events in atomic SQL transactions."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        if (database_url is None) == (engine is None):
            raise ValueError("provide exactly one of database_url or engine")
        if engine is not None:
            self._engine = engine
        else:
            assert database_url is not None
            if database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
            self._engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
        self._clock = clock
        self._id_factory = id_factory

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                inspector = inspect(connection)
                required_tables = ("agents", "approval_requests", "audit_events")
                if not all(inspector.has_table(name) for name in required_tables):
                    return False
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                return revision == REQUIRED_SCHEMA_REVISION
        except SQLAlchemyError:
            return False

    def close(self) -> None:
        self._engine.dispose()

    def register_agent(self, request: AgentRegistrationRequest) -> AgentRecord:
        timestamp = self._clock()
        record = AgentRecord(
            spec=request.spec,
            status=AgentRuntimeStatus.REGISTERED,
            revision=1,
            registered_at=timestamp,
            updated_at=timestamp,
        )
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(agents).values(
                        agent_id=request.spec.agent_id,
                        spec=request.spec.model_dump(mode="json"),
                        status=record.status.value,
                        revision=record.revision,
                        registered_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                self._insert_audit_event(
                    connection,
                    event_type=AuditEventType.AGENT_REGISTERED,
                    agent_id=request.spec.agent_id,
                    actor=request.actor,
                    occurred_at=timestamp,
                    resource_id=request.spec.agent_id,
                    summary=f"Registered agent version {request.spec.version}",
                )
        except IntegrityError as error:
            raise AgentAlreadyExistsError(
                f"agent '{request.spec.agent_id}' is already registered"
            ) from error
        return record

    def get_agent(self, agent_id: str) -> AgentRecord:
        with self._engine.connect() as connection:
            row = self._get_agent_row(connection, agent_id)
        if row is None:
            raise AgentNotFoundError(f"agent '{agent_id}' was not found")
        return self._agent_from_row(row)

    def list_agents(self) -> tuple[AgentRecord, ...]:
        with self._engine.connect() as connection:
            rows = connection.execute(select(agents).order_by(agents.c.agent_id)).mappings()
            return tuple(self._agent_from_row(row) for row in rows)

    def update_agent_status(self, agent_id: str, update_request: AgentStatusUpdate) -> AgentRecord:
        with self._engine.begin() as connection:
            row = self._get_agent_row(connection, agent_id, for_update=True)
            if row is None:
                raise AgentNotFoundError(f"agent '{agent_id}' was not found")
            current = self._agent_from_row(row)
            if current.revision != update_request.expected_revision:
                raise RevisionConflictError(
                    f"expected revision {update_request.expected_revision}, current revision is "
                    f"{current.revision}"
                )
            validate_status_transition(current.status, update_request.status)

            timestamp = self._clock()
            result = connection.execute(
                update(agents)
                .where(
                    agents.c.agent_id == agent_id,
                    agents.c.revision == update_request.expected_revision,
                )
                .values(
                    status=update_request.status.value,
                    revision=current.revision + 1,
                    updated_at=timestamp,
                )
            )
            if result.rowcount != 1:
                raise RevisionConflictError("agent revision changed during the update")
            self._insert_audit_event(
                connection,
                event_type=AuditEventType.AGENT_STATUS_CHANGED,
                agent_id=agent_id,
                actor=update_request.actor,
                occurred_at=timestamp,
                resource_id=agent_id,
                summary=(
                    f"Changed status from {current.status} to {update_request.status}: "
                    f"{update_request.reason}"
                ),
            )
            return current.model_copy(
                update={
                    "status": update_request.status,
                    "revision": current.revision + 1,
                    "updated_at": timestamp,
                }
            )

    def create_approval(self, request: ApprovalRequestCreate) -> ApprovalRecord:
        with self._engine.begin() as connection:
            agent_row = self._get_agent_row(connection, request.agent_id, for_update=True)
            if agent_row is None:
                raise AgentNotFoundError(f"agent '{request.agent_id}' was not found")
            validate_agent_is_active(self._agent_from_row(agent_row))

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
            connection.execute(insert(approval_requests).values(**record.model_dump(mode="python")))
            self._insert_audit_event(
                connection,
                event_type=AuditEventType.APPROVAL_REQUESTED,
                agent_id=request.agent_id,
                actor=request.actor,
                occurred_at=timestamp,
                resource_id=str(request_id),
                summary=f"Requested {request.risk} approval for {request.action}",
            )
            return record

    def get_approval(self, request_id: UUID) -> ApprovalRecord:
        with self._engine.connect() as connection:
            row = self._get_approval_row(connection, request_id)
        if row is None:
            raise ApprovalNotFoundError(f"approval request '{request_id}' was not found")
        return self._approval_from_row(row)

    def list_approvals(
        self, status: ApprovalStatus | None = None, agent_id: str | None = None
    ) -> tuple[ApprovalRecord, ...]:
        statement = select(approval_requests)
        if status is not None:
            statement = statement.where(approval_requests.c.status == status.value)
        if agent_id is not None:
            statement = statement.where(approval_requests.c.agent_id == agent_id)
        statement = statement.order_by(
            approval_requests.c.created_at, approval_requests.c.request_id
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return tuple(self._approval_from_row(row) for row in rows)

    def decide_approval(
        self, request_id: UUID, decision: ApprovalDecisionRequest
    ) -> ApprovalRecord:
        with self._engine.begin() as connection:
            row = self._get_approval_row(connection, request_id, for_update=True)
            if row is None:
                raise ApprovalNotFoundError(f"approval request '{request_id}' was not found")
            current = self._approval_from_row(row)
            if current.status is not ApprovalStatus.PENDING:
                raise ApprovalAlreadyDecidedError(
                    f"approval request '{request_id}' has already been decided"
                )

            timestamp = self._clock()
            requested_status = (
                ApprovalStatus.APPROVED
                if decision.decision is ApprovalDecision.APPROVE
                else ApprovalStatus.REJECTED
            )
            result = connection.execute(
                update(approval_requests)
                .where(
                    approval_requests.c.request_id == request_id,
                    approval_requests.c.status == ApprovalStatus.PENDING.value,
                )
                .values(
                    status=requested_status.value,
                    decided_at=timestamp,
                    decided_by=decision.actor,
                    decision_reason=decision.reason,
                )
            )
            if result.rowcount != 1:
                raise ApprovalAlreadyDecidedError(
                    f"approval request '{request_id}' was decided concurrently"
                )
            self._insert_audit_event(
                connection,
                event_type=(
                    AuditEventType.APPROVAL_APPROVED
                    if requested_status is ApprovalStatus.APPROVED
                    else AuditEventType.APPROVAL_REJECTED
                ),
                agent_id=current.agent_id,
                actor=decision.actor,
                occurred_at=timestamp,
                resource_id=str(request_id),
                summary=(
                    f"{requested_status.value.capitalize()} {current.action}: {decision.reason}"
                ),
            )
            return current.model_copy(
                update={
                    "status": requested_status,
                    "decided_at": timestamp,
                    "decided_by": decision.actor,
                    "decision_reason": decision.reason,
                }
            )

    def list_audit_events(
        self, agent_id: str | None = None, limit: int = 100
    ) -> tuple[AuditEvent, ...]:
        statement = select(audit_events)
        if agent_id is not None:
            statement = statement.where(audit_events.c.agent_id == agent_id)
        statement = statement.order_by(audit_events.c.sequence.desc()).limit(limit)
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return tuple(self._audit_from_row(row) for row in rows)

    @staticmethod
    def _get_agent_row(
        connection: Connection, agent_id: str, *, for_update: bool = False
    ) -> RowMapping | None:
        statement = select(agents).where(agents.c.agent_id == agent_id)
        if for_update:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    @staticmethod
    def _get_approval_row(
        connection: Connection, request_id: UUID, *, for_update: bool = False
    ) -> RowMapping | None:
        statement = select(approval_requests).where(approval_requests.c.request_id == request_id)
        if for_update:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def _insert_audit_event(
        self,
        connection: Connection,
        *,
        event_type: AuditEventType,
        agent_id: str,
        actor: str,
        occurred_at: datetime,
        resource_id: str,
        summary: str,
    ) -> None:
        connection.execute(
            insert(audit_events).values(
                event_id=self._id_factory(),
                event_type=event_type.value,
                agent_id=agent_id,
                actor=actor,
                occurred_at=occurred_at,
                resource_id=resource_id,
                summary=summary,
            )
        )

    @staticmethod
    def _agent_from_row(row: RowMapping) -> AgentRecord:
        return AgentRecord(
            spec=AgentSpec.model_validate(row["spec"]),
            status=AgentRuntimeStatus(row["status"]),
            revision=row["revision"],
            registered_at=_ensure_timezone(row["registered_at"]),
            updated_at=_ensure_timezone(row["updated_at"]),
        )

    @staticmethod
    def _approval_from_row(row: RowMapping) -> ApprovalRecord:
        return ApprovalRecord(
            request_id=row["request_id"],
            agent_id=row["agent_id"],
            action=row["action"],
            risk=row["risk"],
            status=row["status"],
            requested_by=row["requested_by"],
            request_reason=row["request_reason"],
            created_at=_ensure_timezone(row["created_at"]),
            decided_at=_ensure_timezone(row["decided_at"]),
            decided_by=row["decided_by"],
            decision_reason=row["decision_reason"],
        )

    @staticmethod
    def _audit_from_row(row: RowMapping) -> AuditEvent:
        return AuditEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            agent_id=row["agent_id"],
            actor=row["actor"],
            occurred_at=_ensure_timezone(row["occurred_at"]),
            resource_id=row["resource_id"],
            summary=row["summary"],
        )


@overload
def _ensure_timezone(value: datetime) -> datetime: ...


@overload
def _ensure_timezone(value: None) -> None: ...


def _ensure_timezone(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
