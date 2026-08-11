import json
import secrets

import pytest

from agent_control_plane.auth import Permission, StaticBearerAuthenticator, hash_bearer_token
from agent_control_plane.bootstrap import (
    create_authenticator_from_environment,
    create_runtime_from_environment,
    create_store_from_environment,
)
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


def authentication_environment(token: str) -> dict[str, str]:
    return {
        "ACP_AUTH_CONFIG": json.dumps(
            {
                "principals": [
                    {
                        "subject": "operator@example.test",
                        "token_sha256": hash_bearer_token(token),
                        "permissions": [Permission.ALL],
                    }
                ]
            }
        )
    }


def test_bootstrap_builds_static_authentication_from_json() -> None:
    token = secrets.token_urlsafe(32)

    authenticator = create_authenticator_from_environment(authentication_environment(token))

    assert isinstance(authenticator, StaticBearerAuthenticator)
    assert authenticator.authenticate(token).subject == "operator@example.test"


def test_bootstrap_rejects_invalid_authentication_json() -> None:
    with pytest.raises(ValueError, match="ACP_AUTH_CONFIG is invalid"):
        create_authenticator_from_environment({"ACP_AUTH_CONFIG": "not-json"})


def test_durable_runtime_requires_authentication() -> None:
    database_environment = {
        "ACP_DATABASE_URL": "postgresql+psycopg://user:password@localhost/database"
    }

    with pytest.raises(ValueError, match="ACP_AUTH_CONFIG is required"):
        create_runtime_from_environment(database_environment)

    token = secrets.token_urlsafe(32)
    runtime = create_runtime_from_environment(
        database_environment | authentication_environment(token)
    )
    assert runtime.authenticator.enabled is True
    runtime.store.close()


def test_runtime_requires_an_explicit_insecure_development_mode() -> None:
    with pytest.raises(ValueError, match="ACP_ALLOW_INSECURE_DEV=true"):
        create_runtime_from_environment({})

    runtime = create_runtime_from_environment({"ACP_ALLOW_INSECURE_DEV": "true"})
    assert isinstance(runtime.store, InMemoryControlPlaneStore)
    assert runtime.authenticator.enabled is False
    runtime.store.close()
