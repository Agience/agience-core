def test_jwks_publishes_one_rsa_key(client):
    resp = client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "keys" in body
    assert len(body["keys"]) == 1
    key = body["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert key["kid"]
    assert key["n"]
    assert key["e"]


def test_openid_configuration_exposes_issuer_and_endpoints(client):
    resp = client.get("/.well-known/openid-configuration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["issuer"]
    assert body["jwks_uri"].endswith("/.well-known/jwks.json")
    assert body["authorization_endpoint"].endswith("/auth/authorize")
    assert body["token_endpoint"].endswith("/auth/token")
    assert "RS256" in body["id_token_signing_alg_values_supported"]
    assert "client_credentials" in body["grant_types_supported"]
    assert "authorization_code" in body["grant_types_supported"]
    assert "refresh_token" in body["grant_types_supported"]
    # token-exchange (RFC 8693 delegation) is added when Mantle → Chorus delegation
    # flow lands in a follow-up — not yet wired.
