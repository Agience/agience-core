from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent / "_shared"))
sys.path.insert(0, str(_HERE.parent))

import server as ophan


def _operator_claims(*, entitlements: list[str], workspaces: object = "*") -> dict[str, object]:
    return {
        "sub": "user-123",
        "client_id": "vscode-mcp",
        "scopes": [f"licensing:entitlement:{entitlement}" for entitlement in entitlements],
        "resource_filters": {
            "workspaces": workspaces,
        },
    }


@pytest.mark.asyncio
async def test_issue_license_rejects_missing_entitlements(monkeypatch):
    monkeypatch.setattr(ophan, "_profile_required_entitlements", lambda _profile: {"host_standard"})
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(entitlements=["host_standard"])
    )

    try:
        result = await ophan.issue_license(
            workspace_id="ws-123",
            policy_id="standard-hosted-core",
            account_id="acct-123",
            profile="standard",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    assert result.startswith("Error: ")
    assert "Missing required entitlements" in result
    assert "licensing_operations" in result


@pytest.mark.asyncio
async def test_resolve_license_posture_returns_community_for_qualifying_organization(monkeypatch):
    token = ophan._set_current_operator_claims_for_test(_operator_claims(entitlements=[]))

    async def fake_list_workspace_artifacts(_workspace_id: str):
        return [
            {
                "id": "org-1",
                "context": {
                    "content_type": ophan.ORGANIZATION_CARD_MIME,
                    "identity": {
                        "legal_name": "Acme Research Lab",
                        "entity_kind": "company",
                    },
                    "licensing": {
                        "compliance": {
                            "proprietary_modifications": False,
                            "closed_source_service": False,
                            "source_disclosed": True,
                        },
                        "packaging": {
                            "offers_managed_service": False,
                            "offers_hosted_service": False,
                            "offers_oem": False,
                            "offers_embedded": False,
                            "offers_white_label": False,
                        },
                    },
                },
            }
        ]

    monkeypatch.setattr(ophan, "_list_workspace_artifacts", fake_list_workspace_artifacts)

    try:
        result = await ophan.resolve_license_posture(
            workspace_id="ws-123",
            organization_artifact_id="org-1",
            profile="standard",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["requires_license"] is False
    assert payload["decision"] == "community"
    assert payload["resolved_profile"] == "community-self-host"
    assert payload["resolved_policy_id"] == "community-self-host-core"


@pytest.mark.asyncio
async def test_issue_license_returns_not_required_for_community_eligible_organization(monkeypatch):
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(entitlements=["host_standard", "licensing_operations", "delegated_licensing_operations"])
    )

    async def fake_list_workspace_artifacts(_workspace_id: str):
        return [
            {
                "id": "org-1",
                "context": {
                    "content_type": ophan.ORGANIZATION_CARD_MIME,
                    "identity": {
                        "legal_name": "Small Nonprofit",
                        "entity_kind": "nonprofit",
                    },
                    "licensing": {
                        "compliance": {
                            "proprietary_modifications": False,
                            "closed_source_service": False,
                            "source_disclosed": True,
                        },
                        "packaging": {
                            "offers_managed_service": False,
                            "offers_hosted_service": False,
                            "offers_oem": False,
                            "offers_embedded": False,
                            "offers_white_label": False,
                        },
                    },
                },
            }
        ]

    monkeypatch.setattr(ophan, "_list_workspace_artifacts", fake_list_workspace_artifacts)

    try:
        result = await ophan.issue_license(
            workspace_id="ws-123",
            policy_id="standard-hosted-core",
            account_id="acct-123",
            profile="standard",
            organization_artifact_id="org-1",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["status"] == "not_required"
    assert payload["posture"]["decision"] == "community"
    assert payload["posture"]["resolved_profile"] == "community-self-host"


@pytest.mark.asyncio
async def test_issue_license_creates_entitlement_license_and_event_cards(monkeypatch):
    created: list[dict] = []
    ids = iter(["aaaa11111111", "bbbb22222222"])
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(
            entitlements=["host_standard", "licensing_operations", "delegated_licensing_operations"]
        )
    )

    async def fake_create_workspace_artifact(workspace_id: str, context: dict, content: str):
        created.append({"workspace_id": workspace_id, "context": context, "content": content})
        return {"id": f"card-{len(created)}"}

    monkeypatch.setattr(ophan, "uuid4", lambda: SimpleNamespace(hex=next(ids)))
    monkeypatch.setattr(ophan, "_now_iso", lambda: "2026-03-07T12:00:00Z")
    monkeypatch.setattr(ophan, "_future_iso", lambda _days: "2027-03-07T12:00:00Z")
    monkeypatch.setattr(ophan, "_profile_required_entitlements", lambda _profile: {"host_standard"})
    monkeypatch.setattr(ophan, "_profile_license_class", lambda _profile: "commercial-self-host")
    monkeypatch.setattr(ophan, "_profile_surface", lambda _profile: "core-app")
    monkeypatch.setattr(ophan, "_load_profile", lambda _profile: {"offline_supported": True, "meter_dimensions": ["mai"]})
    monkeypatch.setattr(
        ophan,
        "_issue_signed_license_artifact",
        lambda **_kwargs: {
            "schema_version": "1",
            "license_id": "lic_bbbb22222222",
            "entitlement_id": "ent_aaaa11111111",
            "account_id": "acct-123",
            "issued_at": "2026-03-07T12:00:00Z",
            "not_before": "2026-03-07T12:00:00Z",
            "expires_at": "2027-03-07T12:00:00Z",
            "product": {
                "policy_id": "standard-hosted-core",
                "runtime_roles": ["standard"],
                "distribution_profiles": ["standard"],
                "product_surface": "core-app",
            },
            "controls": {
                "offline_allowed": True,
                "offline_lease_days": 30,
                "require_activation": True,
                "require_reporting": True,
                "enforcement_profile": "commercial-self-host",
            },
            "entitlements": ["host_standard"],
            "signature": {"alg": "EdDSA", "kid": "lic-2026-q1", "value": "sig"},
        },
    )
    monkeypatch.setattr(ophan, "_artifact_digest", lambda _payload: "sha256:test-artifact")
    monkeypatch.setattr(ophan, "_create_workspace_artifact", fake_create_workspace_artifact)

    try:
        result = await ophan.issue_license(
            workspace_id="ws-123",
            policy_id="standard-hosted-core",
            account_id="acct-123",
            profile="standard",
            limits=json.dumps({"max_active_instances": 3}),
            features=json.dumps({"allow_white_label": False}),
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["status"] == "issued"
    assert payload["workspace_id"] == "ws-123"
    assert payload["entitlement_id"] == "ent_aaaa11111111"
    assert payload["license_id"] == "lic_bbbb22222222"
    assert payload["created_cards"] == {
        "entitlement_artifact_id": "card-1",
        "license_artifact_id": "card-2",
        "event_artifact_id": "card-3",
    }

    assert [item["context"]["content_type"] for item in created] == [
        ophan.ENTITLEMENT_CARD_MIME,
        ophan.LICENSE_CARD_MIME,
        ophan.EVENT_CARD_MIME,
    ]
    assert created[0]["context"]["operator"] == {
        "subject_id": "user-123",
        "client_id": "vscode-mcp",
        "api_key_id": None,
        "authorized_entitlements": [
            "delegated_licensing_operations",
            "host_standard",
            "licensing_operations",
        ],
    }
    assert created[1]["context"]["control_class"] == "commercial-self-host"
    assert created[1]["context"]["product_surface"] == "core-app"
    assert created[1]["context"]["limits"] == {"max_active_instances": 3}
    assert created[1]["context"]["features"] == {"allow_white_label": False}
    assert created[1]["context"]["artifact_ref"] == "ophan://licenses/lic_bbbb22222222"
    assert created[1]["context"]["artifact_hash"] == "sha256:test-artifact"
    assert created[1]["context"]["signed_artifact"]["license_id"] == "lic_bbbb22222222"


@pytest.mark.asyncio
async def test_review_installation_with_license_issues_activation_lease(monkeypatch):
    updated: dict = {}
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(entitlements=["host_standard"])
    )

    async def fake_list_workspace_artifacts(_workspace_id: str):
        return [
            {
                "id": "license-card-1",
                "context": {
                    "content_type": ophan.LICENSE_CARD_MIME,
                    "license_id": "lic-1",
                    "distribution_profiles": ["standard"],
                    "signed_artifact": {
                        "schema_version": "1",
                        "license_id": "lic-1",
                        "entitlement_id": "ent-1",
                        "account_id": "acct-1",
                        "issued_at": "2026-03-07T00:00:00Z",
                        "not_before": "2026-03-07T00:00:00Z",
                        "expires_at": "2027-03-07T00:00:00Z",
                        "product": {
                            "policy_id": "standard-hosted-core",
                            "runtime_roles": ["standard"],
                            "distribution_profiles": ["standard"],
                            "product_surface": "core-app",
                        },
                        "controls": {
                            "offline_allowed": True,
                            "offline_lease_days": 30,
                            "require_activation": True,
                            "require_reporting": True,
                            "enforcement_profile": "commercial-self-host",
                        },
                        "entitlements": ["host_standard"],
                        "signature": {"alg": "EdDSA", "kid": "lic-2026-q1", "value": "sig"},
                    },
                },
            },
            {
                "id": "install-card-1",
                "context": {
                    "content_type": ophan.INSTALLATION_CARD_MIME,
                    "install_id": "inst-1",
                    "license_id": "lic-1",
                    "profile": "standard",
                    "compliance_state": "active",
                },
            },
        ]

    async def fake_update_workspace_artifact(workspace_id: str, artifact_id: str, *, context: dict, content: str):
        updated["workspace_id"] = workspace_id
        updated["artifact_id"] = artifact_id
        updated["context"] = context
        updated["content"] = content
        return {"id": artifact_id}

    monkeypatch.setattr(ophan, "_list_workspace_artifacts", fake_list_workspace_artifacts)
    monkeypatch.setattr(ophan, "_update_workspace_artifact", fake_update_workspace_artifact)
    monkeypatch.setattr(ophan, "_load_profile", lambda _profile: {"runtime_role": "standard"})
    monkeypatch.setattr(
        ophan,
        "_licensing_service",
        lambda: SimpleNamespace(
            preflight_license=lambda _profile, _artifact: SimpleNamespace(
                verification=SimpleNamespace(valid=True),
                compatibility=SimpleNamespace(allowed=True),
            ),
            digest_signed_payload=lambda _payload: "sha256:test-lease",
        ),
    )
    monkeypatch.setattr(
        ophan,
        "_issue_signed_activation_lease",
        lambda **_kwargs: {
            "schema_version": "1",
            "lease_id": "lease-1",
            "license_id": "lic-1",
            "install_id": "inst-1",
            "runtime_role": "standard",
            "issued_at": "2026-03-07T12:00:00Z",
            "not_before": "2026-03-07T12:00:00Z",
            "lease_expires_at": "2026-04-06T12:00:00Z",
            "profile": "standard",
            "signature": {"alg": "EdDSA", "kid": "lic-2026-q1", "value": "sig"},
        },
    )
    monkeypatch.setattr(ophan, "_now_iso", lambda: "2026-03-07T12:00:00Z")
    monkeypatch.setattr(ophan, "uuid4", lambda: SimpleNamespace(hex="cccc33333333"))

    try:
        result = await ophan.review_installation(
            workspace_id="ws-123",
            install_id="inst-1",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["status"] == "reviewed"
    assert payload["activation_lease"]["lease_id"] == "lease-1"
    assert updated["workspace_id"] == "ws-123"
    assert updated["artifact_id"] == "install-card-1"
    assert updated["context"]["activation_lease_ref"] == "ophan://leases/lease-1"
    assert updated["context"]["activation_lease_hash"] == "sha256:test-lease"


@pytest.mark.asyncio
async def test_review_installation_without_identity_returns_summary(monkeypatch):
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(entitlements=["host_standard"])
    )

    async def fake_list_workspace_artifacts(_workspace_id: str):
        return [
            {
                "id": "card-install-1",
                "context": {
                    "content_type": ophan.INSTALLATION_CARD_MIME,
                    "install_id": "inst-1",
                    "license_id": "lic-1",
                    "profile": "standard",
                    "compliance_state": "active",
                    "lease_expires_at": "2026-04-01T00:00:00Z",
                },
            },
            {
                "id": "card-other",
                "context": {"content_type": ophan.LICENSE_CARD_MIME},
            },
        ]

    monkeypatch.setattr(ophan, "_list_workspace_artifacts", fake_list_workspace_artifacts)

    try:
        result = await ophan.review_installation(
            workspace_id="ws-123",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["installations"] == [
        {
            "artifact_id": "card-install-1",
            "install_id": "inst-1",
            "license_id": "lic-1",
            "profile": "standard",
            "compliance_state": "active",
            "lease_expires_at": "2026-04-01T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_run_licensing_report_counts_cards_and_persists_report(monkeypatch):
    captured: dict = {}
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(entitlements=["licensing_operations", "delegated_licensing_operations"])
    )

    async def fake_list_workspace_artifacts(_workspace_id: str):
        return [
            {"context": {"content_type": ophan.ENTITLEMENT_CARD_MIME}},
            {"context": {"content_type": ophan.LICENSE_CARD_MIME, "state": "active"}},
            {"context": {"content_type": ophan.LICENSE_CARD_MIME, "state": "revoked"}},
            {"context": {"content_type": ophan.EVENT_CARD_MIME, "severity": "warning"}},
        ]

    async def fake_create_workspace_artifact(workspace_id: str, context: dict, content: str):
        captured["workspace_id"] = workspace_id
        captured["context"] = context
        captured["content"] = content
        return {"id": "report-card-1"}

    monkeypatch.setattr(ophan, "_list_workspace_artifacts", fake_list_workspace_artifacts)
    monkeypatch.setattr(ophan, "_create_workspace_artifact", fake_create_workspace_artifact)
    monkeypatch.setattr(ophan, "_now_iso", lambda: "2026-03-07T12:30:00Z")

    try:
        result = await ophan.run_licensing_report(
            workspace_id="ws-123",
            report_type="renewals",
        )
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    payload = json.loads(result)
    assert payload["status"] == "generated"
    assert payload["report_artifact_id"] == "report-card-1"
    assert payload["summary"]["counts"] == {
        "entitlements": 1,
        "licenses": 2,
        "installations": 0,
        "usage_snapshots": 0,
        "events": 1,
    }
    assert payload["summary"]["active_licenses"] == 1
    assert payload["summary"]["revoked_licenses"] == 1
    assert payload["summary"]["warning_events"] == 1

    assert captured["workspace_id"] == "ws-123"
    assert captured["context"]["content_type"] == "text/markdown"
    assert captured["context"]["report_type"] == "renewals"
    assert "# Licensing Report — renewals" in captured["content"]
    assert "- Active licenses: 1" in captured["content"]


def test_resolve_operator_entitlements_enforces_workspace_scope():
    token = ophan._set_current_operator_claims_for_test(
        _operator_claims(
            entitlements=["licensing_operations"],
            workspaces=["ws-allowed"],
        )
    )

    try:
        with pytest.raises(ophan.OphanToolError) as exc:
            ophan._resolve_operator_entitlements("ws-denied", "run_licensing_report")
    finally:
        ophan._reset_current_operator_claims_for_test(token)

    assert "cannot access workspace 'ws-denied'" in str(exc.value)