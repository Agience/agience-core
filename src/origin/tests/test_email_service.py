"""Unit tests for Origin's email service config resolution.

Regression guard: SMTP `username` and SES `access_key_id` are persisted as
PLAIN platform settings by both writers — the setup wizard and the manifest
applier classify only keys containing password/secret/api_key/token/credential
as secret. email_service must therefore read them with ``get()``, not
``get_secret()``; otherwise the credentials come back empty and SMTP/SES auth
silently fails — the "email not populated from config" symptom.
"""

from __future__ import annotations

import pytest

from origin.services import email_service
from origin.services.platform_settings_service import _SettingsCache


@pytest.fixture(autouse=True)
def _clear_email_env(monkeypatch):
    """Isolate from the real .env (which may set EMAIL_PROVIDER / GOOGLE_OAUTH_*).
    Each test opts into env fallbacks explicitly via monkeypatch.setenv."""
    for var in (
        "EMAIL_PROVIDER",
        "PLATFORM_EMAIL_ADDRESS",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
        "SMTP_HOST",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def smtp_cache(monkeypatch) -> _SettingsCache:
    cache = _SettingsCache()
    # Plain values — exactly how the wizard / manifest persist them.
    cache._values.update(
        {
            "email.provider": "smtp",
            "email.from_address": "noreply@example.com",
            "email.from_name": "Acme",
            "email.smtp.host": "smtp.example.com",
            "email.smtp.port": "2525",
            "email.smtp.username": "mailer@example.com",
            "email.smtp.use_tls": "true",
        }
    )
    # Secrets — encrypted at rest, read via get_secret().
    cache._secrets.update({"email.smtp.password": "s3cr3t"})
    monkeypatch.setattr(email_service, "settings", cache)
    return cache


def test_smtp_username_read_from_plain_settings(smtp_cache):
    cfg = email_service._get_provider_config()
    # The regression: username must not be empty when configured.
    assert cfg["smtp_username"] == "mailer@example.com"
    assert cfg["smtp_password"] == "s3cr3t"
    assert cfg["smtp_host"] == "smtp.example.com"
    assert cfg["smtp_port"] == 2525
    assert cfg["smtp_use_tls"] is True
    assert cfg["from_address"] == "noreply@example.com"
    assert cfg["from_name"] == "Acme"


def test_ses_access_key_id_read_from_plain_settings(monkeypatch):
    cache = _SettingsCache()
    cache._values.update(
        {
            "email.provider": "ses",
            "email.ses.region": "ca-central-1",
            "email.ses.access_key_id": "AKIAEXAMPLE",
        }
    )
    cache._secrets.update({"email.ses.secret_access_key": "ses-secret"})
    monkeypatch.setattr(email_service, "settings", cache)

    cfg = email_service._get_provider_config()
    # The regression: access_key_id must not be empty when configured.
    assert cfg["ses_access_key_id"] == "AKIAEXAMPLE"
    assert cfg["ses_secret_access_key"] == "ses-secret"
    assert cfg["ses_region"] == "ca-central-1"


def test_is_configured_tracks_provider(monkeypatch):
    cache = _SettingsCache()
    monkeypatch.setattr(email_service, "settings", cache)
    assert email_service.is_configured() is False
    cache._values["email.provider"] = "smtp"
    assert email_service.is_configured() is True


# ---------------------------------------------------------------------------
# Gmail provider (OAuth2 — reuses the platform's Google OAuth app)
# ---------------------------------------------------------------------------


def _gmail_cache() -> _SettingsCache:
    cache = _SettingsCache()
    cache._values.update(
        {
            "email.provider": "gmail",
            "email.from_address": "ops@example.com",
            "email.from_name": "Acme",
            "auth.google.client_id": "cid",
        }
    )
    cache._secrets.update(
        {
            "auth.google.client_secret": "csecret",
            "auth.google.refresh_token": "rtoken",
        }
    )
    return cache


def test_gmail_is_configured_requires_google_creds(monkeypatch):
    cache = _gmail_cache()
    monkeypatch.setattr(email_service, "settings", cache)
    assert email_service.is_configured() is True

    # Drop the refresh token → no longer configured (can't mint access tokens).
    cache._secrets.pop("auth.google.refresh_token")
    assert email_service.is_configured() is False


def test_provider_and_gmail_config_fall_back_to_env(monkeypatch):
    cache = _SettingsCache()  # nothing persisted to the DB cache
    monkeypatch.setattr(email_service, "settings", cache)
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "envcid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "envcs")
    monkeypatch.setenv("GOOGLE_OAUTH_REFRESH_TOKEN", "envrt")

    assert email_service._provider() == "gmail"
    assert email_service._gmail_config() == {
        "client_id": "envcid",
        "client_secret": "envcs",
        "refresh_token": "envrt",
    }
    assert email_service.is_configured() is True


@pytest.mark.asyncio
async def test_gmail_send_exchanges_token_then_calls_gmail_api(monkeypatch):
    monkeypatch.setattr(email_service, "settings", _gmail_cache())

    calls: list[tuple[str, dict]] = []

    class _FakeResp:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            return None

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if url == email_service._GMAIL_TOKEN_URL:
                return _FakeResp({"access_token": "ya29.test"})
            return _FakeResp({"id": "msg-1"})

    monkeypatch.setattr(email_service.httpx, "AsyncClient", _FakeAsyncClient)

    ok = await email_service.send_email("to@example.com", "Hi", "<b>hi</b>", "hi")
    assert ok is True

    # 1) refresh token exchanged at Google's token endpoint
    assert calls[0][0] == email_service._GMAIL_TOKEN_URL
    assert calls[0][1]["data"]["grant_type"] == "refresh_token"
    assert calls[0][1]["data"]["refresh_token"] == "rtoken"
    # 2) message sent via the Gmail API with the minted bearer token
    assert calls[1][0] == email_service._GMAIL_SEND_URL
    assert calls[1][1]["headers"]["Authorization"] == "Bearer ya29.test"
    assert "raw" in calls[1][1]["json"]
