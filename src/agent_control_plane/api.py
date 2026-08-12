"""HTTP surface for the control-plane contract."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agent_control_plane import __version__
from agent_control_plane.auth import (
    AuthenticatedPrincipal,
    AuthenticationError,
    Authenticator,
    DisabledAuthenticator,
    Permission,
)
from agent_control_plane.bootstrap import ControlPlaneRuntime, create_runtime_from_environment
from agent_control_plane.models import (
    AgentRecord,
    AgentRegistrationRequest,
    AgentSpec,
    AgentSpecValidationResponse,
    AgentStatusUpdate,
    ApprovalDecisionRequest,
    ApprovalQueueResponse,
    ApprovalRecord,
    ApprovalRequestCreate,
    ApprovalStatus,
    AuditEventPage,
    HealthResponse,
    HealthStatus,
)
from agent_control_plane.store import (
    AgentAlreadyExistsError,
    AgentNotActiveError,
    AgentNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ControlPlaneStore,
    InMemoryControlPlaneStore,
    InvalidStatusTransitionError,
    RevisionConflictError,
)

SERVICE_NAME = "agent-control-plane"
bearer_scheme = HTTPBearer(auto_error=False)
PermissionDependency = Callable[
    [HTTPAuthorizationCredentials | None], AuthenticatedPrincipal | None
]


def _raise_http_error(
    status_code: int,
    code: str,
    error: Exception,
    *,
    headers: dict[str, str] | None = None,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
        headers=headers,
    ) from error


def _permission_dependency(
    authenticator: Authenticator,
    permission: Permission,
) -> PermissionDependency:
    def require_permission(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(bearer_scheme),
        ] = None,
    ) -> AuthenticatedPrincipal | None:
        if not authenticator.enabled:
            return None
        try:
            principal = authenticator.authenticate(
                credentials.credentials if credentials is not None else None
            )
        except AuthenticationError as error:
            _raise_http_error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_failed",
                error,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if principal is None:
            _raise_http_error(
                status.HTTP_401_UNAUTHORIZED,
                "authentication_failed",
                AuthenticationError("bearer authentication failed"),
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not principal.allows(permission):
            _raise_http_error(
                status.HTTP_403_FORBIDDEN,
                "permission_denied",
                PermissionError(f"permission '{permission}' is required"),
            )
        return principal

    return require_permission


def _validate_actor(principal: AuthenticatedPrincipal | None, claimed_actor: str) -> None:
    if principal is not None and principal.subject != claimed_actor:
        _raise_http_error(
            status.HTTP_403_FORBIDDEN,
            "actor_mismatch",
            PermissionError("request actor must match the authenticated subject"),
        )


def create_app(
    store: ControlPlaneStore | None = None,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    control_plane = store if store is not None else InMemoryControlPlaneStore()
    auth = authenticator if authenticator is not None else DisabledAuthenticator()
    agents_read = _permission_dependency(auth, Permission.AGENTS_READ)
    agents_write = _permission_dependency(auth, Permission.AGENTS_WRITE)
    approvals_read = _permission_dependency(auth, Permission.APPROVALS_READ)
    approvals_request = _permission_dependency(auth, Permission.APPROVALS_REQUEST)
    approvals_decide = _permission_dependency(auth, Permission.APPROVALS_DECIDE)
    audit_read = _permission_dependency(auth, Permission.AUDIT_READ)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        control_plane.close()

    application = FastAPI(
        title="Agent Control Plane",
        description="Reliability and governance APIs for production AI agents.",
        version=__version__,
        lifespan=lifespan,
    )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status=HealthStatus.OK, service=SERVICE_NAME, version=__version__)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    def readiness() -> HealthResponse:
        if not control_plane.is_ready():
            _raise_http_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "store_unavailable",
                RuntimeError("control-plane store is unavailable or not migrated"),
            )
        return HealthResponse(status=HealthStatus.OK, service=SERVICE_NAME, version=__version__)

    @application.post(
        "/v1/agent-specs/validate",
        response_model=AgentSpecValidationResponse,
        tags=["agent-specs"],
    )
    async def validate_agent_spec(
        spec: AgentSpec,
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(agents_read)],
    ) -> AgentSpecValidationResponse:
        return AgentSpecValidationResponse(
            valid=True,
            agent_id=spec.agent_id,
            schema_version=spec.schema_version,
        )

    @application.post(
        "/v1/agents",
        response_model=AgentRecord,
        status_code=status.HTTP_201_CREATED,
        tags=["agents"],
    )
    def register_agent(
        request: AgentRegistrationRequest,
        principal: Annotated[AuthenticatedPrincipal | None, Depends(agents_write)],
    ) -> AgentRecord:
        _validate_actor(principal, request.actor)
        try:
            return control_plane.register_agent(request)
        except AgentAlreadyExistsError as error:
            _raise_http_error(status.HTTP_409_CONFLICT, "agent_already_exists", error)

    @application.get("/v1/agents", response_model=list[AgentRecord], tags=["agents"])
    def list_agents(
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(agents_read)],
    ) -> tuple[AgentRecord, ...]:
        return control_plane.list_agents()

    @application.get("/v1/agents/{agent_id}", response_model=AgentRecord, tags=["agents"])
    def get_agent(
        agent_id: str,
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(agents_read)],
    ) -> AgentRecord:
        try:
            return control_plane.get_agent(agent_id)
        except AgentNotFoundError as error:
            _raise_http_error(status.HTTP_404_NOT_FOUND, "agent_not_found", error)

    @application.patch(
        "/v1/agents/{agent_id}/status",
        response_model=AgentRecord,
        tags=["agents"],
    )
    def update_agent_status(
        agent_id: str,
        update: AgentStatusUpdate,
        principal: Annotated[AuthenticatedPrincipal | None, Depends(agents_write)],
    ) -> AgentRecord:
        _validate_actor(principal, update.actor)
        try:
            return control_plane.update_agent_status(agent_id, update)
        except AgentNotFoundError as error:
            _raise_http_error(status.HTTP_404_NOT_FOUND, "agent_not_found", error)
        except RevisionConflictError as error:
            _raise_http_error(status.HTTP_409_CONFLICT, "revision_conflict", error)
        except InvalidStatusTransitionError as error:
            _raise_http_error(status.HTTP_409_CONFLICT, "invalid_status_transition", error)

    @application.post(
        "/v1/approvals",
        response_model=ApprovalRecord,
        status_code=status.HTTP_201_CREATED,
        tags=["approvals"],
    )
    def create_approval(
        request: ApprovalRequestCreate,
        principal: Annotated[AuthenticatedPrincipal | None, Depends(approvals_request)],
    ) -> ApprovalRecord:
        _validate_actor(principal, request.actor)
        try:
            return control_plane.create_approval(request)
        except AgentNotFoundError as error:
            _raise_http_error(status.HTTP_404_NOT_FOUND, "agent_not_found", error)
        except AgentNotActiveError as error:
            _raise_http_error(status.HTTP_409_CONFLICT, "agent_not_active", error)

    @application.get(
        "/v1/approvals/{request_id}", response_model=ApprovalRecord, tags=["approvals"]
    )
    def get_approval(
        request_id: UUID,
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(approvals_read)],
    ) -> ApprovalRecord:
        try:
            return control_plane.get_approval(request_id)
        except ApprovalNotFoundError as error:
            _raise_http_error(status.HTTP_404_NOT_FOUND, "approval_not_found", error)

    @application.get("/v1/approvals", response_model=ApprovalQueueResponse, tags=["approvals"])
    def list_approvals(
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(approvals_read)],
        approval_status: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
        agent_id: str | None = None,
    ) -> ApprovalQueueResponse:
        items = control_plane.list_approvals(status=approval_status, agent_id=agent_id)
        return ApprovalQueueResponse(items=items, count=len(items))

    @application.post(
        "/v1/approvals/{request_id}/decision",
        response_model=ApprovalRecord,
        tags=["approvals"],
    )
    def decide_approval(
        request_id: UUID,
        decision: ApprovalDecisionRequest,
        principal: Annotated[AuthenticatedPrincipal | None, Depends(approvals_decide)],
    ) -> ApprovalRecord:
        _validate_actor(principal, decision.actor)
        try:
            return control_plane.decide_approval(request_id, decision)
        except ApprovalNotFoundError as error:
            _raise_http_error(status.HTTP_404_NOT_FOUND, "approval_not_found", error)
        except ApprovalAlreadyDecidedError as error:
            _raise_http_error(status.HTTP_409_CONFLICT, "approval_already_decided", error)

    @application.get("/v1/audit-events", response_model=AuditEventPage, tags=["audit"])
    def list_audit_events(
        _principal: Annotated[AuthenticatedPrincipal | None, Depends(audit_read)],
        agent_id: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> AuditEventPage:
        items = control_plane.list_audit_events(agent_id=agent_id, limit=limit)
        return AuditEventPage(items=items, count=len(items))

    return application


def create_app_from_environment() -> FastAPI:
    runtime: ControlPlaneRuntime = create_runtime_from_environment()
    return create_app(runtime.store, runtime.authenticator)
