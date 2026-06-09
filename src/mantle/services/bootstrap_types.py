"""
Bootstrap constants — kernel-known-at-init slugs, content types, and list fixtures.

OS analogy: These are the filesystem formats and mount points the kernel must
understand to boot.  The kernel knows these constants at init time so it can
create the initial platform collections and singleton artifacts during startup.

No other Core code should reference content type strings or slug strings directly —
all runtime type resolution flows through the type registry (types_service) and
the ID registry (platform_topology).

Consumed by the declarative seed loader (`seed_provisioning.loader` /
`seed_provisioning.user_provisioning`) and `platform_topology` — slugs map seed
artifacts to their stable UUIDs and drive per-user grant/materialization.

Do NOT add new entries here unless the constant is required for platform bootstrap.
Content types that are not created at startup belong to their owning MCP server.
"""

# ---------------------------------------------------------------------------
# Content types — required for bootstrap artifact creation only
# ---------------------------------------------------------------------------

AUTHORITY_CONTENT_TYPE = "application/vnd.agience.authority+json"
HOST_CONTENT_TYPE = "application/vnd.agience.host+json"
AGENCY_CONTENT_TYPE = "application/vnd.agience.agency+json"
AGENT_CONTENT_TYPE = "application/vnd.agience.agent+json"
LLM_CONNECTION_CONTENT_TYPE = "application/vnd.agience.llm-connection+json"
MCP_SERVER_CONTENT_TYPE = "application/vnd.agience.mcp-server+json"
PACKAGE_CONTENT_TYPE = "application/vnd.agience.package+json"
# MANTLE anchor — a fully-disclosed reference point. The AnchorSet is a
# collection of these; they are the routing centroids of encrypted search.
ANCHOR_CONTENT_TYPE = "application/vnd.agience.anchor+json"

# ---------------------------------------------------------------------------
# Collection slugs — stable human-readable IDs for idempotent bootstrap lookup
# ---------------------------------------------------------------------------

AUTHORITY_COLLECTION_SLUG = "agience-authorities"
HOST_COLLECTION_SLUG = "agience-hosts"
RESOURCES_COLLECTION_SLUG = "agience-resources"
INBOX_SEEDS_COLLECTION_SLUG = "agience-inbox-seeds"

# Seed sub-collections — populated at startup, granted READ to new users on first login
START_HERE_COLLECTION_SLUG = "agience-seeds-start-here"
PLATFORM_ARTIFACTS_COLLECTION_SLUG = "agience-seeds-platform-artifacts"
ALL_SERVERS_COLLECTION_SLUG = "agience-seeds-all-servers"
ALL_TOOLS_COLLECTION_SLUG = "agience-seeds-all-tools"
AGENTS_COLLECTION_SLUG = "agience-seeds-agents"

LLM_CONNECTIONS_COLLECTION_SLUG = "agience-llm-connections"

# The shared AnchorSet — a collection whose members are anchor artifacts (the
# routing centroids of MANTLE encrypted search + grounding for Anchored
# reasoning). Seeded empty; the MANTLE bootstrap populates + grows it. Granted
# READ to every user (it is common grounded knowledge).
ANCHORSET_COLLECTION_SLUG = "agience-anchorset"

# Package registry — committed package manifests that have been published
# for discovery. Shown in the marketplace browse UI and queryable via the
# standard artifact search. Empty at first boot; populated as users publish.
PACKAGE_REGISTRY_COLLECTION_SLUG = "agience-package-registry"

# (The operator is identified by the `platform.operator_id` setting — there is
# no operator *collection*. Operator access is the admin grant issued by
# `_ensure_operator_bootstrapped` on every platform collection.)

# ---------------------------------------------------------------------------
# Artifact slugs
# ---------------------------------------------------------------------------

AUTHORITY_ARTIFACT_SLUG = "agience-authority-current-instance"
HOST_ARTIFACT_SLUG = "agience-host-current-instance"
AGENCY_ARTIFACT_SLUG = "agience-agency-platform"
AGENT_ARTIFACT_SLUG_PREFIX = "agience-agent-"
LLM_CONNECTION_SLUG_PREFIX = "agience-llm-"
# The kernel MCP server (backend/mcp_server/) is always available.
# It gets a stable UUID via platform_topology like every other platform entity.
AGIENCE_CORE_SLUG = "agience-core"

# Phase 7 — Server Artifact Proxy. First-party MCP servers are seeded as
# vnd.agience.mcp-server+json artifacts at bootstrap. Slug format: agience-server-{name}
# (matching the client_id used by kernel server credentials).
SERVER_ARTIFACT_SLUG_PREFIX = "agience-server-"

# ---------------------------------------------------------------------------
# Agent persona slugs (used to derive artifact slugs)
# ---------------------------------------------------------------------------

PLATFORM_AGENT_SLUGS = [
    "aria", "astra", "sage", "iris",
    "ophan", "seraph", "verso",
]

PLATFORM_LLM_CONNECTION_SLUGS = [
    "anthropic-sonnet",
    "anthropic-haiku",
    "anthropic-opus",
]

# ---------------------------------------------------------------------------
# Seed collection fixture lists
# ---------------------------------------------------------------------------

# Collections granted READ to every new user on first login
USER_READABLE_SEED_SLUGS = [
    INBOX_SEEDS_COLLECTION_SLUG,
    START_HERE_COLLECTION_SLUG,
    PLATFORM_ARTIFACTS_COLLECTION_SLUG,
    ALL_SERVERS_COLLECTION_SLUG,
    ALL_TOOLS_COLLECTION_SLUG,
    AGENTS_COLLECTION_SLUG,
    LLM_CONNECTIONS_COLLECTION_SLUG,
    PACKAGE_REGISTRY_COLLECTION_SLUG,
    ANCHORSET_COLLECTION_SLUG,
]

# Collections whose committed artifacts are materialized into the user's inbox workspace.
# Inbox Seeds currently contains curated collection artifacts (for example Start Here and
# Platform Artifacts). Their member artifacts remain in their own collections and are not
# flattened into every inbox workspace.
INBOX_MATERIALIZATION_SLUGS = [INBOX_SEEDS_COLLECTION_SLUG]

# All platform-owned collections (used for admin grants and ID pre-resolution)
ALL_PLATFORM_COLLECTION_SLUGS = [
    AUTHORITY_COLLECTION_SLUG,
    HOST_COLLECTION_SLUG,
    RESOURCES_COLLECTION_SLUG,
    INBOX_SEEDS_COLLECTION_SLUG,
    START_HERE_COLLECTION_SLUG,
    PLATFORM_ARTIFACTS_COLLECTION_SLUG,
    ALL_SERVERS_COLLECTION_SLUG,
    ALL_TOOLS_COLLECTION_SLUG,
    AGENTS_COLLECTION_SLUG,
    LLM_CONNECTIONS_COLLECTION_SLUG,
    PACKAGE_REGISTRY_COLLECTION_SLUG,
    ANCHORSET_COLLECTION_SLUG,
]
