import pytest

from agent_control_plane.bootstrap import create_store_from_environment
from agent_control_plane.postgres_store import PostgresControlPlaneStore
from agent_control_plane.store import InMemoryControlPlaneStore


def test_bootstrap_uses_memory_without_a_database_url() -> None:
    store = create_store_from_environment({})

    assert isinstance(store, InMemoryControlPlaneStore)


def test_bootstrap_builds_postgres_store_for_a_database_url() -> None:
    store = create_store_from_environment(
        {"ACP_DATABASE_URL": "postgresql+psycopg://user:password@localhost/database"}
    )

    assert isinstance(store, PostgresControlPlaneStore)
    store.close()


def test_bootstrap_rejects_non_postgres_urls() -> None:
    with pytest.raises(ValueError, match="must be a PostgreSQL URL"):
        create_store_from_environment({"ACP_DATABASE_URL": "sqlite:///control-plane.db"})
