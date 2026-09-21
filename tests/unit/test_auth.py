import secrets

import pytest
from pydantic import ValidationError

from agent_control_plane.auth import (
    AuthenticatedPrincipal,
    AuthenticationConfig,
    AuthenticationError,
    DisabledAuthenticator,
    Permission,
    StaticBearerAuthenticator,
    TokenPrincipalConfig,
    hash_bearer_token,
)


def config_for(token: str, *permissions: Permission) -> AuthenticationConfig:
    return AuthenticationConfig(
        principals=(
            TokenPrincipalConfig(
                subject="operator@example.test",
                token_sha256=hash_bearer_token(token),
                permissions=frozenset(permissions),
            ),
        )
    )


def test_disabled_authenticator_is_explicitly_inactive() -> None:
    authenticator = DisabledAuthenticator()

    assert authenticator.enabled is False
    assert authenticator.authenticate(None) is None


def test_static_authenticator_resolves_a_token_fingerprint() -> None:
    token = secrets.token_urlsafe(32)
    authenticator = StaticBearerAuthenticator(config_for(token, Permission.AGENTS_READ))

    assert authenticator.enabled is True
    assert authenticator.authenticate(token) == AuthenticatedPrincipal(
        subject="operator@example.test",
        permissions=frozenset({Permission.AGENTS_READ}),
    )


def test_missing_and_invalid_tokens_have_the_same_failure() -> None:
    valid_token = secrets.token_urlsafe(32)
    authenticator = StaticBearerAuthenticator(config_for(valid_token, Permission.AGENTS_READ))

    for token in (None, secrets.token_urlsafe(32)):
        with pytest.raises(AuthenticationError, match="bearer authentication failed"):
            authenticator.authenticate(token)


def test_permissions_are_explicit_with_an_admin_wildcard() -> None:
    reader = AuthenticatedPrincipal(
        subject="reader@example.test",
        permissions=frozenset({Permission.AGENTS_READ}),
    )
    admin = AuthenticatedPrincipal(
        subject="admin@example.test",
        permissions=frozenset({Permission.ALL}),
    )

    assert reader.allows(Permission.AGENTS_READ) is True
    assert reader.allows(Permission.AGENTS_WRITE) is False
    assert admin.allows(Permission.APPROVALS_DECIDE) is True


def test_authentication_config_rejects_duplicate_token_fingerprints() -> None:
    token_hash = hash_bearer_token(secrets.token_urlsafe(32))
    principal = TokenPrincipalConfig(
        subject="operator@example.test",
        token_sha256=token_hash,
        permissions=frozenset({Permission.ALL}),
    )

    with pytest.raises(ValidationError, match="token fingerprints must be unique"):
        AuthenticationConfig(principals=(principal, principal))
