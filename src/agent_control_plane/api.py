"""HTTP surface for the initial control-plane contract."""

from fastapi import FastAPI

from agent_control_plane import __version__
from agent_control_plane.models import (
    AgentSpec,
    AgentSpecValidationResponse,
    HealthResponse,
    HealthStatus,
)

SERVICE_NAME = "agent-control-plane"


def create_app() -> FastAPI:
    application = FastAPI(
        title="Agent Control Plane",
        description="Reliability and governance APIs for production AI agents.",
        version=__version__,
    )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status=HealthStatus.OK, service=SERVICE_NAME, version=__version__)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse:
        # Dependency checks will be added here as durable stores are introduced.
        return HealthResponse(status=HealthStatus.OK, service=SERVICE_NAME, version=__version__)

    @application.post(
        "/v1/agent-specs/validate",
        response_model=AgentSpecValidationResponse,
        tags=["agent-specs"],
    )
    async def validate_agent_spec(spec: AgentSpec) -> AgentSpecValidationResponse:
        return AgentSpecValidationResponse(
            valid=True,
            agent_id=spec.agent_id,
            schema_version=spec.schema_version,
        )

    return application


app = create_app()
