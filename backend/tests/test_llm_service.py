"""Unit tests for services.llm_service.

Covers the workspace → user → environment fallback chain for LLM API key
resolution, plus workspace-context CRUD wrappers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services import llm_service


class TestGetLlmKeyForWorkspace:
    def _patch_arango(self):
        return patch("services.llm_service.get_arango_db", return_value=iter([MagicMock()]))

    def test_workspace_specific_key_wins(self):
        with (
            self._patch_arango(),
            patch(
                "services.workspace_service.get_workspace_context",
                return_value={"llm": {"key_id": "secret-1"}},
            ),
            patch(
                "services.secrets_service.get_secret_value",
                return_value="ws-key",
            ) as get_secret,
        ):
            out = llm_service.get_llm_key_for_workspace(
                MagicMock(), "user-1", "ws-1", provider="openai"
            )
        assert out == "ws-key"
        # Called with the secret_id from the workspace context.
        assert get_secret.call_args.kwargs["secret_id"] == "secret-1"

    def test_user_default_when_no_workspace_key(self):
        """Workspace has no llm.key_id → router skips workspace lookup and
        falls through to the user-default secret."""
        with (
            self._patch_arango(),
            patch(
                "services.workspace_service.get_workspace_context",
                return_value={},
            ),
            patch(
                "services.secrets_service.get_secret_value",
                return_value="user-default",
            ) as get_secret,
        ):
            out = llm_service.get_llm_key_for_workspace(
                MagicMock(), "user-1", "ws-1", provider="openai"
            )
        assert out == "user-default"
        # Only the user-default lookup ran (no secret_id passed).
        assert get_secret.call_count == 1
        assert get_secret.call_args.kwargs.get("secret_id") is None

    def test_falls_back_to_env_openai_key(self):
        with (
            self._patch_arango(),
            patch(
                "services.workspace_service.get_workspace_context", return_value={}
            ),
            patch(
                "services.secrets_service.get_secret_value", return_value=None
            ),
            patch("core.config.OPENAI_API_KEY", "sk-env-default"),
        ):
            out = llm_service.get_llm_key_for_workspace(
                MagicMock(), "user-1", "ws-1", provider="openai"
            )
        assert out == "sk-env-default"

    def test_returns_none_for_unknown_provider(self):
        with (
            self._patch_arango(),
            patch(
                "services.workspace_service.get_workspace_context", return_value={}
            ),
            patch(
                "services.secrets_service.get_secret_value", return_value=None
            ),
        ):
            out = llm_service.get_llm_key_for_workspace(
                MagicMock(), "user-1", "ws-1", provider="anthropic"
            )
        # No env fallback for non-openai providers.
        assert out is None

    def test_workspace_context_exception_falls_through(self):
        with (
            self._patch_arango(),
            patch(
                "services.workspace_service.get_workspace_context",
                side_effect=RuntimeError("ws lookup failed"),
            ),
            patch(
                "services.secrets_service.get_secret_value",
                return_value="user-default",
            ),
        ):
            out = llm_service.get_llm_key_for_workspace(
                MagicMock(), "user-1", "ws-1", provider="openai"
            )
        # Exception in workspace lookup is swallowed; user-default still resolved.
        assert out == "user-default"


class TestSetWorkspaceLlm:
    def test_writes_llm_block_into_context(self):
        captured = {}

        def fake_update(db, user_id, ws_id, ctx):
            captured["context"] = ctx

        with (
            patch(
                "services.workspace_service.get_workspace_context", return_value={}
            ),
            patch(
                "services.workspace_service.update_workspace_context",
                side_effect=fake_update,
            ),
        ):
            llm_service.set_workspace_llm(
                MagicMock(),
                "user-1",
                "ws-1",
                provider="openai",
                model="gpt-4o",
                key_id="secret-1",
            )
        assert captured["context"]["llm"] == {
            "provider": "openai",
            "model": "gpt-4o",
            "key_id": "secret-1",
        }

    def test_handles_non_dict_context(self):
        with (
            patch(
                "services.workspace_service.get_workspace_context", return_value=None
            ),
            patch(
                "services.workspace_service.update_workspace_context"
            ) as upd,
        ):
            llm_service.set_workspace_llm(
                MagicMock(), "user-1", "ws-1", provider="openai", model="gpt-4o"
            )
        # Falls back to {} and writes the llm block.
        ctx = upd.call_args[0][3]
        assert ctx["llm"]["model"] == "gpt-4o"


class TestClearWorkspaceLlm:
    def test_removes_llm_block(self):
        captured = {}

        def fake_update(db, user_id, ws_id, ctx):
            captured["context"] = ctx

        with (
            patch(
                "services.workspace_service.get_workspace_context",
                return_value={"llm": {"provider": "openai"}, "other": "stuff"},
            ),
            patch(
                "services.workspace_service.update_workspace_context",
                side_effect=fake_update,
            ),
        ):
            llm_service.clear_workspace_llm(MagicMock(), "user-1", "ws-1")
        assert "llm" not in captured["context"]
        assert captured["context"]["other"] == "stuff"

    def test_noop_when_no_llm_block(self):
        with (
            patch(
                "services.workspace_service.get_workspace_context",
                return_value={"other": "stuff"},
            ),
            patch(
                "services.workspace_service.update_workspace_context"
            ) as upd,
        ):
            llm_service.clear_workspace_llm(MagicMock(), "user-1", "ws-1")
        upd.assert_not_called()

    def test_noop_when_context_is_none(self):
        with (
            patch(
                "services.workspace_service.get_workspace_context", return_value=None
            ),
            patch(
                "services.workspace_service.update_workspace_context"
            ) as upd,
        ):
            llm_service.clear_workspace_llm(MagicMock(), "user-1", "ws-1")
        upd.assert_not_called()
