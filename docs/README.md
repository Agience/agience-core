# Agience Documentation

Status: **Reference**
Date: 2026-04-10

Agience is a human-in-the-loop knowledge curation platform — an OS-like substrate where AI agents and humans collaborate over structured, versioned information through open MCP standards.

---

## New to Agience?

- [What is Agience?](overview/what-is-agience.md) — Start here: core concepts, goals, and the information triangle
- [Quickstart](getting-started/quickstart.md) — Get running in minutes

---

## Overview

| Document | Description |
|---|---|
| [What is Agience?](overview/what-is-agience.md) | Core concepts, goals, and the information triangle |
| [Platform Overview](overview/platform-overview.md) | High-level architecture, layer model, and key components |
| [Information OS Analogy](overview/information-os-analogy.md) | How Agience relates to an operating system for knowledge |
| [Manifesto](overview/manifesto.md) | The principles and philosophy behind Agience |
| [Solution Taxonomy](overview/solution-taxonomy.md) | How solutions, personas, and content types are organized |

---

## Use Cases

| Document | Description |
|---|---|
| [Use Cases](use-cases/README.md) | Overview of all documented use cases |
| [Email Management](use-cases/email-management.md) | Intelligent email triage and response with AI agents |
| [Personal Assistant](use-cases/personal-assistant.md) | Telegram-based personal AI assistant |
| [Meeting Intelligence](use-cases/meeting-intelligence.md) | Capturing and surfacing knowledge from meetings |
| [Executive AI Team](use-cases/executive-ai-team.md) | Multi-agent coordination for executive workflows |
| [Event Planning](use-cases/event-planning.md) | AI-assisted event coordination and logistics |

---

## Getting Started

| Document | Description |
|---|---|
| [Quickstart](getting-started/quickstart.md) | Fastest path to a running Agience instance |
| [Local Development](getting-started/local-development.md) | Full dev setup with Docker, backend, and frontend |
| [Self-Hosting Guide](getting-started/self-hosting.md) | Run Agience on your own infrastructure |
| [Deploy to EC2](getting-started/deploy-ec2.md) | Step-by-step EC2 deployment walkthrough |
| [Admin Setup](getting-started/admin-setup.md) | First-run admin configuration and provisioning |

For MCP client configuration, see [MCP Client Setup](mcp/client-setup.md).

---

## Architecture

| Document | Description |
|---|---|
| [Architecture Overview](architecture/overview.md) | System architecture: services, databases, and communication patterns |
| [Layered Architecture](architecture/layered-architecture.md) | Core / Handlers / Presentation layer boundaries and rules |
| [Artifact Model](architecture/artifact-model.md) | Artifact structure, versioning, references, and ArangoDB lifecycle |
| [Content Types](architecture/content-types.md) | MIME-based content type system and handler ownership model |
| [Security Model](architecture/security-model.md) | Auth, JWT, API keys, scopes, grants, and trust model |

---

## Features

| Document | Description |
|---|---|
| [Search](features/search.md) | Hybrid BM25 + semantic search, aperture control, query language |
| [Agent Execution](features/agent-execution.md) | Agent artifacts, operator execution, and invocation API |
| [Desktop Host Relay](features/desktop-host-relay.md) | Local MCP bridge via WebSocket relay for desktop apps |
| [Workspace Automation](features/workspace-automation.md) | Event handlers, workspace triggers, and automation patterns |
| [External Auth](features/external-auth.md) | Connecting external identity providers (OAuth, OIDC) |
| [Content Type Registry](features/content-type-registry.md) | How content types are registered, resolved, and served |

---

## MCP Integration

| Document | Description |
|---|---|
| [MCP Overview](mcp/overview.md) | How Agience acts as both MCP server and MCP client |
| [Client Setup](mcp/client-setup.md) | Connecting an MCP client to Agience |
| [Client Instructions](mcp/client-instructions.md) | Tool surface reference for external MCP clients |
| [Server Development](mcp/server-development.md) | Build and register MCP servers: auth, callbacks, content types |
| [Testing](mcp/testing.md) | How to test MCP tools and server connections |
| [VS Code](mcp/vscode-extension.md) | Using Agience as an MCP server inside VS Code |

---

## Reference

| Document | Description |
|---|---|
| [Vocabulary](reference/vocabulary.md) | Canonical term definitions (Artifact, Card, Operator, etc.) |
| [API Reference](api/README.md) | Backend REST API endpoint reference |

---

## Guides

| Document | Description |
|---|---|
| [Best Practices](guides/best-practices.md) | Coding conventions, testing, and anti-patterns |
| [Component Guide](guides/component-guide.md) | Frontend component inventory and usage patterns |
| [Color Standards](guides/color-standards.md) | Design system color palette and usage rules |
| [CI/CD Pipeline](guides/ci-cd.md) | Build, test, and deployment pipeline overview |

---

## Contributing

| Document | Description |
|---|---|
| [Contributing](contributing.md) | How to contribute code, docs, and content types |
| [Changelog](changelog.md) | Release history and version notes |
