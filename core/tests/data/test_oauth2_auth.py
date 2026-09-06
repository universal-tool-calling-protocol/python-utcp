"""``OAuth2Auth.cache_key``: the identity of a credential configuration.

This key is the single source of the rule that every communication protocol
uses to cache and coalesce tokens, so its semantics are pinned here: two
configurations share a key exactly when they would obtain the same token.
"""

from utcp.data.auth_implementations import OAuth2Auth


def _auth(**overrides) -> OAuth2Auth:
    fields = dict(
        auth_type="oauth2",
        token_url="https://issuer-a.example/token",
        client_id="client",
        client_secret="secret",
        scope="read",
    )
    fields.update(overrides)
    return OAuth2Auth(**fields)


def test_identical_configurations_share_a_key():
    assert _auth().cache_key() == _auth().cache_key()


def test_every_token_affecting_field_changes_the_key():
    base = _auth().cache_key()
    assert _auth(token_url="https://issuer-b.example/token").cache_key() != base
    assert _auth(client_id="other").cache_key() != base
    assert _auth(client_secret="other").cache_key() != base
    assert _auth(scope="write").cache_key() != base


def test_same_client_id_at_a_different_issuer_does_not_share_a_key():
    # The flaw this rule exists to prevent: a shared client_id must never let
    # two configurations receive each other's tokens.
    a = _auth(token_url="https://issuer-a.example/token")
    b = _auth(token_url="https://issuer-b.example/token")
    assert a.client_id == b.client_id
    assert a.cache_key() != b.cache_key()


def test_absent_scope_normalises_to_empty():
    assert _auth(scope=None).cache_key() == _auth(scope="").cache_key()
