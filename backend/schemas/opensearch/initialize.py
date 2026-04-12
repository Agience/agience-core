# schemas/opensearch/initialize.py
"""
Provision the agience app user and role in OpenSearch Security.

Runs at startup using the bootstrap admin credentials. Creates:
  - Role `agience-app-role`: read/write/admin on cards_* indices only; no cluster admin.
  - User `agience-app` (or whatever OPENSEARCH_USERNAME is set to): password = OPENSEARCH_PASSWORD.
  - Role mapping: user -> role.

Idempotent -- safe to run on every restart.
"""
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("schemas.opensearch.initialize")

# Index patterns the app user is allowed to touch
APP_INDEX_PATTERNS = ["artifacts", "artifacts*"]

APP_ROLE_NAME = "agience-app-role"

# Minimal cluster permissions for non-admin app operation.
# Without this, `cluster.health` and other informational calls will 403.
APP_CLUSTER_PERMISSIONS = [
    "cluster:monitor/health",
]

# Permissions required by the app:
#   - documents: read + write (search, index, delete)
#   - index admin: create, delete, refresh, get settings, update settings
APP_INDEX_PERMISSIONS = [
    "indices:data/read/*",
    "indices:data/write/*",
    "indices:admin/create",
    "indices:admin/delete",
    "indices:admin/get",
    "indices:admin/refresh",
    "indices:admin/settings/update",
    "indices:admin/mapping/put",
    "indices:admin/aliases*",
    "indices:monitor/*",
]


def _make_admin_client():
    """Build a one-shot client using the bootstrap admin credentials."""
    from opensearchpy import OpenSearch
    from core import config

    admin_pwd = os.getenv("OPENSEARCH_INITIAL_ADMIN_PASSWORD")
    if not admin_pwd:
        raise RuntimeError(
            "OPENSEARCH_INITIAL_ADMIN_PASSWORD is not set. "
            "Cannot provision OpenSearch app user without the bootstrap admin password."
        )

    return OpenSearch(
        hosts=[{"host": config.OPENSEARCH_HOST, "port": config.OPENSEARCH_PORT}],
        scheme="https" if config.OPENSEARCH_USE_SSL else "http",
        use_ssl=config.OPENSEARCH_USE_SSL,
        verify_certs=config.OPENSEARCH_VERIFY_CERTS if config.OPENSEARCH_USE_SSL else False,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
        http_auth=("admin", admin_pwd),
        basic_auth=("admin", admin_pwd),
    )


def _role_exists(client, role_name: str) -> bool:
    try:
        resp = client.transport.perform_request(
            "GET", f"/_plugins/_security/api/roles/{role_name}"
        )
        return role_name in resp
    except Exception:
        return False


def _user_exists(client, username: str) -> bool:
    try:
        resp = client.transport.perform_request(
            "GET", f"/_plugins/_security/api/internalusers/{username}"
        )
        return username in resp
    except Exception:
        return False


def _create_or_update_role(client):
    body = {
        "cluster_permissions": APP_CLUSTER_PERMISSIONS,
        "index_permissions": [
            {
                "index_patterns": APP_INDEX_PATTERNS,
                "allowed_actions": APP_INDEX_PERMISSIONS,
            }
        ],
        "tenant_permissions": [],
    }
    client.transport.perform_request(
        "PUT", f"/_plugins/_security/api/roles/{APP_ROLE_NAME}", body=body
    )
    logger.info(f"OpenSearch: provisioned role '{APP_ROLE_NAME}'")


def _create_user(client, username: str, password: str):
    body = {
        "password": password,
        "opendistro_security_roles": [],
    }
    client.transport.perform_request(
        "PUT", f"/_plugins/_security/api/internalusers/{username}", body=body
    )
    logger.info(f"OpenSearch: provisioned user '{username}'")


def _map_role(client, username: str):
    body = {
        "users": [username],
    }
    client.transport.perform_request(
        "PUT", f"/_plugins/_security/api/rolesmapping/{APP_ROLE_NAME}", body=body
    )
    logger.info(f"OpenSearch: mapped '{username}' -> '{APP_ROLE_NAME}'")


def init_opensearch_security(app_username: Optional[str] = None, app_password: Optional[str] = None):
    """
    Provision the app user and role using admin bootstrap credentials.

    Called at startup before init_search_indices(). Idempotent.

    Args:
        app_username: Defaults to OPENSEARCH_USERNAME env var.
        app_password:  Defaults to OPENSEARCH_PASSWORD env var.
    """
    username = app_username or os.getenv("OPENSEARCH_USERNAME", "")
    password = app_password or os.getenv("OPENSEARCH_PASSWORD", "")

    force_password_sync = os.getenv("OPENSEARCH_PROVISION_FORCE_PASSWORD", "false").lower() == "true"
    deadline_s = float(os.getenv("OPENSEARCH_SECURITY_PROVISION_DEADLINE_S", "30"))

    # If username is 'admin' -- the operator has opted to run as the built-in
    # admin account. Nothing to provision; skip silently.
    if not username or username == "admin":
        if username == "admin":
            logger.info("OpenSearch: running as built-in 'admin' user -- skipping app-user provisioning.")
        else:
            logger.warning("OPENSEARCH_USERNAME is not set -- skipping OpenSearch security provisioning.")
        return

    if not password:
        logger.warning(
            f"OPENSEARCH_PASSWORD is not set for user '{username}' -- "
            "skipping OpenSearch security provisioning. Set OPENSEARCH_PASSWORD in .env."
        )
        return

    try:
        client = _make_admin_client()

        start = time.time()
        attempt = 0
        while True:
            attempt += 1
            try:
                # 1. Create/update the role (always update to pick up permission changes)
                _create_or_update_role(client)

                # 2. Create or (optionally) update the user
                if not _user_exists(client, username):
                    _create_user(client, username, password)
                else:
                    if force_password_sync:
                        _create_user(client, username, password)
                        logger.info(f"OpenSearch: user '{username}' exists -- password updated (OPENSEARCH_PROVISION_FORCE_PASSWORD=true).")
                    else:
                        logger.info(
                            f"OpenSearch: user '{username}' already exists -- skipping password update. "
                            "(Set OPENSEARCH_PROVISION_FORCE_PASSWORD=true to force-sync the password from env.)"
                        )

                # 3. Ensure role mapping is current
                _map_role(client, username)

                logger.info(f" OpenSearch security provisioning complete for user '{username}'")
                return

            except Exception as e:
                msg = str(e).lower()
                is_transient = (
                    "security not initialized" in msg
                    or "opensearch security not initialized" in msg
                    or "ssl" in msg
                    or "connection" in msg
                    or "eof" in msg
                )
                elapsed = time.time() - start
                if is_transient and elapsed < deadline_s:
                    sleep_s = min(0.5 * attempt, 3.0)
                    logger.warning(
                        "OpenSearch not ready yet (%s). Retrying provisioning in %.1fs... (%.1fs elapsed)",
                        type(e).__name__,
                        sleep_s,
                        elapsed,
                    )
                    time.sleep(sleep_s)
                    continue
                raise

    except RuntimeError as e:
        logger.warning(f"OpenSearch security provisioning skipped: {e}")
    except Exception as e:
        logger.error(f"OpenSearch security provisioning failed: {e}", exc_info=True)
        # Non-fatal -- app can still start if the user already exists from a previous run
