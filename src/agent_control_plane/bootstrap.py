"""Environment-driven adapter selection for the service process."""

import os
from collections.abc import Mapping

from agent_control_plane.postgres_store import PostgresControlPlaneStore
from agent_control_plane.store import ControlPlaneStore, InMemoryControlPlaneStore

DATABASE_URL_ENV = "ACP_DATABASE_URL"


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
