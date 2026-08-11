"""Versioned public contracts for agents and service health."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class AgentSpec(BaseModel):
    """Minimal, framework-neutral contract used to register an agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default="v1", pattern=r"^v[1-9][0-9]*$")
    agent_id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,62}$")
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
