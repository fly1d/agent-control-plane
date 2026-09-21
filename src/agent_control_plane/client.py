"""Typed synchronous client for the Agent Control Plane HTTP API."""

from types import TracebackType
from typing import Any, Self, TypeVar, overload
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

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
)

ModelT = TypeVar("ModelT", bound=BaseModel)
ResponseT = TypeVar("ResponseT")


class ControlPlaneClientError(Exception):
    """Base class for SDK failures."""


class ControlPlaneTransportError(ControlPlaneClientError):
    """Raised when the control plane cannot be reached."""


class ControlPlaneResponseError(ControlPlaneClientError):
    """Raised when a successful response violates the expected contract."""


class ControlPlaneAPIError(ControlPlaneClientError):
    """Structured error returned by the control-plane API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(f"{status_code} {code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


class ControlPlaneClient:
    """Call current control-plane contracts without hand-building HTTP requests."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        bearer_token: str | None = None,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if http_client is not None and bearer_token is not None:
            raise ValueError("bearer_token cannot be combined with an injected http_client")
        if http_client is None:
            headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
            self._http = httpx.Client(
                base_url=base_url.rstrip("/"),
                headers=headers,
                timeout=timeout,
            )
            self._owns_http_client = True
        else:
            self._http = http_client
            self._owns_http_client = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def live(self) -> HealthResponse:
        return self._request("GET", "/health/live", response_model=HealthResponse)

    def ready(self) -> HealthResponse:
        return self._request("GET", "/health/ready", response_model=HealthResponse)

    def validate_agent_spec(self, spec: AgentSpec) -> AgentSpecValidationResponse:
        return self._request(
            "POST",
            "/v1/agent-specs/validate",
            request_model=spec,
            response_model=AgentSpecValidationResponse,
        )

    def register_agent(self, request: AgentRegistrationRequest) -> AgentRecord:
        return self._request(
            "POST",
            "/v1/agents",
            request_model=request,
            response_model=AgentRecord,
        )

    def list_agents(self) -> tuple[AgentRecord, ...]:
        return self._request(
            "GET",
            "/v1/agents",
            response_model=TypeAdapter(tuple[AgentRecord, ...]),
        )

    def get_agent(self, agent_id: str) -> AgentRecord:
        return self._request(
            "GET",
            f"/v1/agents/{quote(agent_id, safe='')}",
            response_model=AgentRecord,
        )

    def update_agent_status(self, agent_id: str, update: AgentStatusUpdate) -> AgentRecord:
        return self._request(
            "PATCH",
            f"/v1/agents/{quote(agent_id, safe='')}/status",
            request_model=update,
            response_model=AgentRecord,
        )

    def create_approval(self, request: ApprovalRequestCreate) -> ApprovalRecord:
        return self._request(
            "POST",
            "/v1/approvals",
            request_model=request,
            response_model=ApprovalRecord,
        )

    def get_approval(self, request_id: UUID) -> ApprovalRecord:
        return self._request(
            "GET",
            f"/v1/approvals/{request_id}",
            response_model=ApprovalRecord,
        )

    def list_approvals(
        self,
        *,
        status: ApprovalStatus | None = None,
        agent_id: str | None = None,
    ) -> ApprovalQueueResponse:
        params: dict[str, str | int] = {
            key: value
            for key, value in (
                ("status", status.value if status is not None else None),
                ("agent_id", agent_id),
            )
            if value is not None
        }
        return self._request(
            "GET",
            "/v1/approvals",
            params=params,
            response_model=ApprovalQueueResponse,
        )

    def decide_approval(
        self,
        request_id: UUID,
        decision: ApprovalDecisionRequest,
    ) -> ApprovalRecord:
        return self._request(
            "POST",
            f"/v1/approvals/{request_id}/decision",
            request_model=decision,
            response_model=ApprovalRecord,
        )

    def list_audit_events(
        self,
        *,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> AuditEventPage:
        params: dict[str, str | int] = {"limit": limit}
        if agent_id is not None:
            params["agent_id"] = agent_id
        return self._request(
            "GET",
            "/v1/audit-events",
            params=params,
            response_model=AuditEventPage,
        )

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        request_model: BaseModel | None = None,
        params: dict[str, str | int] | None = None,
        response_model: type[ModelT],
    ) -> ModelT: ...

    @overload
    def _request(
        self,
        method: str,
        path: str,
        *,
        request_model: BaseModel | None = None,
        params: dict[str, str | int] | None = None,
        response_model: TypeAdapter[ResponseT],
    ) -> ResponseT: ...

    def _request(
        self,
        method: str,
        path: str,
        *,
        request_model: BaseModel | None = None,
        params: dict[str, str | int] | None = None,
        response_model: type[BaseModel] | TypeAdapter[Any],
    ) -> Any:
        try:
            response = self._http.request(
                method,
                path,
                json=request_model.model_dump(mode="json") if request_model is not None else None,
                params=params,
            )
        except httpx.HTTPError as error:
            raise ControlPlaneTransportError("control-plane request failed") from error

        if not response.is_success:
            raise _api_error(response)
        try:
            payload: Any = response.json()
            if isinstance(response_model, TypeAdapter):
                return response_model.validate_python(payload)
            return response_model.model_validate(payload)
        except (ValueError, ValidationError) as error:
            raise ControlPlaneResponseError(
                f"control plane returned an invalid response for {method} {path}"
            ) from error


def _api_error(response: httpx.Response) -> ControlPlaneAPIError:
    try:
        detail = response.json()["detail"]
        code = detail["code"]
        message = detail["message"]
        if not isinstance(code, str) or not isinstance(message, str):
            raise TypeError
    except (KeyError, TypeError, ValueError):
        code = "http_error"
        message = f"control plane returned HTTP {response.status_code}"
    return ControlPlaneAPIError(response.status_code, code, message)
