"""
tools/migrate_env_to_db.py

One-time migration script for existing deployments.
Reads a .env file and populates the platform_settings table.

Usage:
    cd backend
    python -m tools.migrate_env_to_db [--env-file ../.env] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Mapping: env var name -> (setting key, category, is_secret)
ENV_TO_SETTING = {
    # AI
    "OPENAI_API_KEY": ("ai.openai_api_key", "ai", True),

    # ArangoDB
    "ARANGO_HOST": ("db.arango.host", "db", False),
    "ARANGO_PORT": ("db.arango.port", "db", False),
    "ARANGO_USERNAME": ("db.arango.username", "db", False),
    "ARANGO_ROOT_PASSWORD": ("db.arango.password", "db", True),
    "ARANGO_DATABASE": ("db.arango.database", "db", False),

    # Google OAuth
    "GOOGLE_OAUTH_CLIENT_ID": ("auth.google.client_id", "auth", False),
    "GOOGLE_OAUTH_CLIENT_SECRET": ("auth.google.client_secret", "auth", True),
    "GOOGLE_OAUTH_REDIRECT_URI": ("auth.google.redirect_uri", "auth", False),

    # Microsoft
    "MICROSOFT_ENTRA_TENANT": ("auth.microsoft.tenant", "auth", False),
    "MICROSOFT_ENTRA_CLIENT_ID": ("auth.microsoft.client_id", "auth", False),
    "MICROSOFT_ENTRA_CLIENT_SECRET": ("auth.microsoft.client_secret", "auth", True),

    # Auth0
    "AUTH0_DOMAIN": ("auth.auth0.domain", "auth", False),
    "AUTH0_CLIENT_ID": ("auth.auth0.client_id", "auth", False),
    "AUTH0_CLIENT_SECRET": ("auth.auth0.client_secret", "auth", True),

    # Custom OIDC
    "CUSTOM_OIDC_NAME": ("auth.oidc.name", "auth", False),
    "CUSTOM_OIDC_METADATA_URL": ("auth.oidc.metadata_url", "auth", False),
    "CUSTOM_OIDC_CLIENT_ID": ("auth.oidc.client_id", "auth", False),
    "CUSTOM_OIDC_CLIENT_SECRET": ("auth.oidc.client_secret", "auth", True),

    # Password auth
    "PASSWORD_AUTH_ENABLED": ("auth.password.enabled", "auth", False),
    "PASSWORD_MIN_LENGTH": ("auth.password.min_length", "auth", False),

    # Access control
    "ALLOWED_EMAILS": ("auth.allowed_emails", "auth", False),
    "ALLOWED_DOMAINS": ("auth.allowed_domains", "auth", False),

    # Content storage
    "CONTENT_URI": ("storage.content_uri", "storage", False),
    "CONTENT_BUCKET": ("storage.content_bucket", "storage", False),

    # OpenSearch
    "OPENSEARCH_HOST": ("search.opensearch.host", "search", False),
    "OPENSEARCH_PORT": ("search.opensearch.port", "search", False),
    "OPENSEARCH_USERNAME": ("search.opensearch.username", "search", False),
    "OPENSEARCH_PASSWORD": ("search.opensearch.password", "search", True),

    # Search tuning
    "SEARCH_CHUNK_SIZE": ("search.chunk_size", "search", False),
    "SEARCH_CHUNK_OVERLAP": ("search.chunk_overlap", "search", False),
    "SEARCH_FIELD_WEIGHTS_PRESET": ("search.field_weights_preset", "search", False),

    # Branding
    "FRONTEND_URI": ("branding.frontend_uri", "branding", False),
    "VITE_BACKEND_URI": ("branding.backend_uri", "branding", False),

    # Platform
    "BACKEND_LOG_LEVEL": ("platform.log_level", "platform", False),
    "INDEX_QUEUE_MAX_WORKERS": ("platform.index_queue_max_workers", "platform", False),
}


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict, skipping comments and empty lines."""
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser(description="Migrate .env to platform_settings DB")
    parser.add_argument("--env-file", default="../.env", help="Path to .env file")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    if not env_path.exists():
        print(f"Error: {env_path} not found")
        sys.exit(1)

    print(f"Reading: {env_path}")
    env_values = parse_env_file(env_path)
    print(f"Found {len(env_values)} env vars")

    settings_to_write = []
    for env_key, value in env_values.items():
        if env_key in ENV_TO_SETTING:
            setting_key, category, is_secret = ENV_TO_SETTING[env_key]
            settings_to_write.append({
                "key": setting_key,
                "value": value,
                "category": category,
                "is_secret": is_secret,
            })

    print(f"Mapped {len(settings_to_write)} settings to migrate:")
    for s in settings_to_write:
        display_value = "***" if s["is_secret"] else s["value"][:50]
        print(f"  {s['key']} = {display_value}")

    if args.dry_run:
        print("\n[dry-run] No changes written.")
        return

    # Initialize keys and connect to DB
    from core.key_manager import init_encryption_key
    init_encryption_key()

    from core.config import load_bootstrap_settings
    load_bootstrap_settings()

    from schemas.arango.loader import init_arango_db
    arango_db = init_arango_db()

    from services.platform_settings_service import settings as platform_settings

    # Mark setup as complete
    settings_to_write.append({
        "key": "platform.setup_complete",
        "value": "true",
        "category": "platform",
        "is_secret": False,
    })

    count = platform_settings.set_many(arango_db, settings_to_write)
    print(f"\nWritten {count} settings to platform_settings ArangoDB collection.")
    print("Setup marked as complete.")
    print("\nYou can now remove your .env file. All settings are in the database.")


if __name__ == "__main__":
    main()
