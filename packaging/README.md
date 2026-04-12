# Packaging Metadata

Status: **Reference**
Date: 2026-03-31

This directory contains machine-readable metadata for Agience distribution profiles and licensing control classes.

Goals:

- keep distribution packaging declarative
- keep licensing compatibility checks machine-readable
- allow new licensing attributes without changing the overall file layout

Structure:

- `profiles/` defines runtime profiles and their packaging/licensing requirements
- `licensing/` defines control classes and profile-to-policy mappings

Extensibility rules:

- stable top-level fields should remain small and predictable
- forward-looking or product-specific additions should go in `attributes`
- issuer- or deployment-specific additions should go in `extensions`
- unknown keys should generally be ignored by readers unless explicitly marked required by schema version

These files are packaging inputs, not customer licenses.