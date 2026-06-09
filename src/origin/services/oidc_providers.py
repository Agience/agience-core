"""OAuth provider registry for Origin.

Owns the Authlib `OAuth` instance, the `REGISTERED_PROVIDERS` map, and the
`reload_oauth_providers` function (called from lifespan after settings load).

Extracted from Mantle's `routers/auth_router.py` so Origin can construct OAuth
clients independently. Reads provider config (client_id/secret/redirect_uri)
from `core.config` — the values are populated by `config.load_settings_from_db()`
in lifespan, so this must be called after that completes.
"""

from __future__ import annotations

import logging
from typing import Optional

from authlib.integrations.starlette_client import OAuth

from kernel import config

logger = logging.getLogger(__name__)


oauth = OAuth()
REGISTERED_PROVIDERS: dict[str, dict] = {}


def _register_oidc_provider(
    *,
    name: str,
    label: str,
    server_metadata_url: str,
    client_id: Optional[str],
    client_secret: Optional[str],
    redirect_uri: Optional[str],
    scope: str = "openid email profile",
    issuer: Optional[str] = None,
) -> None:
    if not client_id or not redirect_uri:
        return

    register_kwargs: dict = {
        "server_metadata_url": server_metadata_url,
        "client_id": client_id,
        "client_kwargs": {"scope": scope},
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        register_kwargs["client_secret"] = client_secret
    else:
        # Public client (PKCE-only, no secret) — RFC 8252.
        register_kwargs["token_endpoint_auth_method"] = "none"

    oauth.register(name=name, **register_kwargs)
    REGISTERED_PROVIDERS[name] = {
        "label": label,
        "type": "oidc",
        "redirect_uri": redirect_uri,
        "issuer": issuer,
    }


def reload_oauth_providers() -> None:
    """(Re)register all configured OIDC providers from current config values."""
    REGISTERED_PROVIDERS.clear()

    _register_oidc_provider(
        name="google",
        label="Google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=getattr(config, "GOOGLE_OAUTH_CLIENT_ID", None),
        client_secret=getattr(config, "GOOGLE_OAUTH_CLIENT_SECRET", None),
        redirect_uri=getattr(config, "GOOGLE_OAUTH_REDIRECT_URI", None),
        issuer="https://accounts.google.com",
    )

    tenant = getattr(config, "MICROSOFT_ENTRA_TENANT", None) or "common"
    _register_oidc_provider(
        name="entra",
        label="Microsoft",
        server_metadata_url=(
            f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
        ),
        client_id=getattr(config, "MICROSOFT_ENTRA_CLIENT_ID", None),
        client_secret=getattr(config, "MICROSOFT_ENTRA_CLIENT_SECRET", None),
        redirect_uri=getattr(config, "MICROSOFT_ENTRA_REDIRECT_URI", None),
        issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
    )

    auth0_domain = getattr(config, "AUTH0_DOMAIN", None)
    if auth0_domain:
        domain = (
            auth0_domain.strip()
            .removeprefix("https://")
            .removeprefix("http://")
            .strip("/")
        )
        _register_oidc_provider(
            name="auth0",
            label="Auth0",
            server_metadata_url=f"https://{domain}/.well-known/openid-configuration",
            client_id=getattr(config, "AUTH0_CLIENT_ID", None),
            client_secret=getattr(config, "AUTH0_CLIENT_SECRET", None),
            redirect_uri=getattr(config, "AUTH0_REDIRECT_URI", None),
            issuer=f"https://{domain}",
        )

    custom_name = getattr(config, "CUSTOM_OIDC_NAME", None)
    custom_meta = getattr(config, "CUSTOM_OIDC_METADATA_URL", None)
    if custom_name and custom_meta:
        _register_oidc_provider(
            name=custom_name,
            label=custom_name,
            server_metadata_url=custom_meta,
            client_id=getattr(config, "CUSTOM_OIDC_CLIENT_ID", None),
            client_secret=getattr(config, "CUSTOM_OIDC_CLIENT_SECRET", None),
            redirect_uri=getattr(config, "CUSTOM_OIDC_REDIRECT_URI", None),
            scope=getattr(config, "CUSTOM_OIDC_SCOPES", None) or "openid email profile",
        )

    logger.info("OAuth providers (re)registered: %s", sorted(REGISTERED_PROVIDERS))
