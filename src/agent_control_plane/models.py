"""Versioned public contracts for agents, approvals, audit, and service health."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AGENT_ID_PATTERN = r"^[a-z][a-z0-9-]{2,62}$"
ACTION_PATTERN = r"^[a-z][a-z0-9._-]{2,127}$"
ActorId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\s]+$")]


class HealthStatus(StrEnum):
    OK = "ok"


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: HealthStatus
    service: str
    version: str


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentRuntimeStatus(StrEnum):
    REGISTERED = "registered"
    ACTIVE = "active"
    PAUSED = "paused"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class AuditEventType(StrEnum):
    AGENT_REGISTERED = "agent.registered"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"


class AgentSpec(BaseModel):
    """Minimal, framework-neutral contract used to register an agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="v1", pattern=r"^v[1-9][0-9]*$")
    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    entrypoint: str = Field(min_length=1, max_length=500)
    capabilities: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    default_risk: RiskLevel = RiskLevel.MEDIUM

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(capability.strip() for capability in value)
        if any(not capability for capability in normalized):
            raise ValueError("capabilities cannot contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("capabilities must be unique")
        return normalized


class AgentSpecValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    agent_id: str
    schema_version: str


class AgentRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: AgentSpec
    actor: ActorId


class AgentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec: AgentSpec
    status: AgentRuntimeStatus
    revision: int = Field(ge=1)
    registered_at: datetime
    updated_at: datetime


class AgentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AgentRuntimeStatus
    expected_revision: int = Field(ge=1)
    actor: ActorId
    reason: str = Field(min_length=1, max_length=500)


class ApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(pattern=AGENT_ID_PATTERN)
    action: str = Field(pattern=ACTION_PATTERN)
    risk: RiskLevel
    actor: ActorId
    reason: str = Field(min_length=1, max_length=500)


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    agent_id: str
    action: str
    risk: RiskLevel
    status: ApprovalStatus
    requested_by: str
    request_reason: str
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: ApprovalDecision
    actor: ActorId
    reason: str = Field(min_length=1, max_length=500)


class ApprovalQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ApprovalRecord, ...]
    count: int = Field(ge=0)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    event_type: AuditEventType
    agent_id: str
    actor: str
    occurred_at: datetime
    resource_id: str
    summary: str


class AuditEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[AuditEvent, ...]
    count: int = Field(ge=0)
