"""Environment-driven adapter selection for the service process."""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from agent_control_plane.auth import (
    AuthenticationConfig,
    Authenticator,
    DisabledAuthenticator,
    StaticBearerAuthenticator,
)
from agent_control_plane.postgres_store import PostgresControlPlaneStore
from agent_control_plane.store import ControlPlaneStore, InMemoryControlPlaneStore

DATABASE_URL_ENV = "ACP_DATABASE_URL"
AUTH_CONFIG_ENV = "ACP_AUTH_CONFIG"
ALLOW_INSECURE_DEV_ENV = "ACP_ALLOW_INSECURE_DEV"


@dataclass(frozen=True)
class ControlPlaneRuntime:
    store: ControlPlaneStore
    authenticator: Authenticator


def create_store_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ControlPlaneStore:
    values = os.environ if environment is None else environment
    database_url = values.get(DATABASE_URL_ENV)
    if not database_url:
        return InMemoryControlPlaneStore()
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError(f"{DATABASE_URL_ENV} must be a PostgreSQL URL")
    return PostgresControlPlaneStore(database_url)


def create_authenticator_from_environment(
    environment: Mapping[str, str] | None = None,
) -> Authenticator:
    values = os.environ if environment is None else environment
    raw_config = values.get(AUTH_CONFIG_ENV)
    if not raw_config:
        return DisabledAuthenticator()
    try:
        config = AuthenticationConfig.model_validate_json(raw_config)
    except ValidationError as error:
        raise ValueError(f"{AUTH_CONFIG_ENV} is invalid") from error
    return StaticBearerAuthenticator(config)


def create_runtime_from_environment(
    environment: Mapping[str, str] | None = None,
) -> ControlPlaneRuntime:
    values = os.environ if environment is None else environment
    authenticator = create_authenticator_from_environment(values)
    if values.get(DATABASE_URL_ENV) and not authenticator.enabled:
        raise ValueError(f"{AUTH_CONFIG_ENV} is required when {DATABASE_URL_ENV} is configured")
    if not authenticator.enabled and values.get(ALLOW_INSECURE_DEV_ENV) != "true":
        raise ValueError(f"{AUTH_CONFIG_ENV} is required unless {ALLOW_INSECURE_DEV_ENV}=true")
    return ControlPlaneRuntime(
        store=create_store_from_environment(values),
        authenticator=authenticator,
    )
