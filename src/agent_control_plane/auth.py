"""Framework-neutral authentication and permission policy adapters."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_control_plane.models import ActorId


class Permission(StrEnum):
    ALL = "*"
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"
    APPROVALS_READ = "approvals:read"
    APPROVALS_REQUEST = "approvals:request"
    APPROVALS_DECIDE = "approvals:decide"
    AUDIT_READ = "audit:read"


class TokenPrincipalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: ActorId
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    permissions: frozenset[Permission] = Field(min_length=1)


class AuthenticationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principals: tuple[TokenPrincipalConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def token_fingerprints_must_be_unique(self) -> Self:
        fingerprints = [principal.token_sha256 for principal in self.principals]
        if len(fingerprints) != len(set(fingerprints)):
            raise ValueError("token fingerprints must be unique")
        return self


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    permissions: frozenset[Permission]

    def allows(self, permission: Permission) -> bool:
        return Permission.ALL in self.permissions or permission in self.permissions


class AuthenticationError(Exception):
    """Raised when bearer credentials cannot be authenticated."""


class Authenticator(Protocol):
    @property
    def enabled(self) -> bool: ...

    def authenticate(self, token: str | None) -> AuthenticatedPrincipal | None: ...


class DisabledAuthenticator:
    """Explicit development adapter that performs no authentication."""

    @property
    def enabled(self) -> bool:
        return False

    def authenticate(self, token: str | None) -> None:
        return None


class StaticBearerAuthenticator:
    """Authenticate opaque bearer tokens using configured SHA-256 fingerprints."""

    def __init__(self, config: AuthenticationConfig) -> None:
        self._principals = {
            item.token_sha256: AuthenticatedPrincipal(
                subject=item.subject,
                permissions=item.permissions,
            )
            for item in config.principals
        }

    @property
    def enabled(self) -> bool:
        return True

    def authenticate(self, token: str | None) -> AuthenticatedPrincipal:
        if token is None:
            raise AuthenticationError("bearer authentication failed")
        principal = self._principals.get(hash_bearer_token(token))
        if principal is None:
            raise AuthenticationError("bearer authentication failed")
        return principal


def hash_bearer_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
