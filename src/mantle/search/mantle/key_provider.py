"""Pluggable KEK (key-encryption-key) custody for MANTLE master keys.

The master-key store (:class:`search.mantle.oracle.ArangoMasterKeyStore`) persists
per-principal DEKs WRAPPED by the platform KEK. A ``KeyProvider`` abstracts HOW the
wrap/unwrap happens, so the KEK's custody can climb the maturity ladder — local
file → secrets manager → cloud KMS → HSM — WITHOUT changing the search/crypto path.

Two custody models, one interface:
  - **Exportable KEK** (local file, Vault KV, Secrets Manager): the KEK material is
    loaded into this process; wrap/unwrap is local symmetric crypto (Fernet).
  - **Non-exportable KEK** (cloud KMS, HSM, Vault Transit): the KEK NEVER leaves the
    service; the provider calls its Encrypt/Decrypt API. Only the 32-byte DEK
    plaintext transits the wire — never the KEK.

The wrap/unwrap pair is the common denominator of both models. DEKs are 32 bytes —
well under every KMS's ~4 KB direct-encrypt limit — so no extra data-key layer is
needed.

Selected by ``MANTLE_KEK_PROVIDER`` (default ``local``). Scoped to MANTLE master-key
custody today; promote to ``kernel`` for platform-wide KEK use (secrets_service,
etc.) when that's wanted.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)


class KeyProvider(Protocol):
    """Wrap/unwrap a Data Encryption Key (DEK) with the platform KEK."""

    def wrap(self, plaintext: bytes) -> str:
        """Return a storable token for ``plaintext`` (a DEK), protected by the KEK."""

    def unwrap(self, token: str) -> bytes:
        """Recover the DEK from a token produced by :meth:`wrap`."""


class LocalKeyProvider:
    """KEK = the platform ``encryption.key`` on disk (self-host default).

    Wrap/unwrap is local Fernet. Simplest custody: the operator owns the key
    material on their own box. Fine for self-host; for managed SaaS move the KEK
    off-box (KMS/HSM) by selecting another provider.
    """

    def __init__(self, fernet) -> None:
        self._fernet = fernet

    def wrap(self, plaintext: bytes) -> str:
        return self._fernet.encrypt(plaintext).decode()

    def unwrap(self, token: str) -> bytes:
        return self._fernet.decrypt(token.encode())


class AwsKmsKeyProvider:
    """KEK = a NON-exportable AWS KMS key (managed SaaS).

    The DEK plaintext is sent to KMS to be encrypted/decrypted; the KEK never
    enters this process, is IAM-gated, and every use is logged in CloudTrail.

    SKELETON — wired but UNTESTED here (needs ``boto3`` + AWS creds + a KMS key).
    Enable with ``MANTLE_KEK_PROVIDER=kms`` and ``MANTLE_KMS_KEY_ID=<arn|key-id>``.
    """

    def __init__(self, key_id: str, client=None) -> None:
        if not key_id:
            raise ValueError("AwsKmsKeyProvider requires MANTLE_KMS_KEY_ID")
        self._key_id = key_id
        self._client = client  # built lazily so boto3 is a SaaS-only dependency

    def _kms(self):
        if self._client is None:
            import boto3  # SaaS-only dependency
            self._client = boto3.client("kms")
        return self._client

    def wrap(self, plaintext: bytes) -> str:
        resp = self._kms().encrypt(KeyId=self._key_id, Plaintext=plaintext)
        return base64.b64encode(resp["CiphertextBlob"]).decode()

    def unwrap(self, token: str) -> bytes:
        resp = self._kms().decrypt(KeyId=self._key_id, CiphertextBlob=base64.b64decode(token))
        return resp["Plaintext"]


class VaultTransitKeyProvider:
    """KEK = a HashiCorp Vault Transit key (non-exportable; Vault does the crypto).

    SKELETON — wired but UNTESTED here (needs a reachable Vault + token + a transit
    key). Enable with ``MANTLE_KEK_PROVIDER=vault`` and ``VAULT_ADDR`` /
    ``VAULT_TOKEN`` / ``MANTLE_VAULT_TRANSIT_KEY``.
    """

    def __init__(self, addr: str, token: str, key_name: str) -> None:
        if not (addr and token and key_name):
            raise ValueError(
                "VaultTransitKeyProvider requires VAULT_ADDR, VAULT_TOKEN, MANTLE_VAULT_TRANSIT_KEY"
            )
        self._addr = addr.rstrip("/")
        self._token = token
        self._key = key_name

    def _post(self, op: str, payload: dict) -> dict:
        import httpx
        resp = httpx.post(
            f"{self._addr}/v1/transit/{op}/{self._key}",
            headers={"X-Vault-Token": self._token},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"]

    def wrap(self, plaintext: bytes) -> str:
        data = self._post("encrypt", {"plaintext": base64.b64encode(plaintext).decode()})
        return data["ciphertext"]  # "vault:v1:..."

    def unwrap(self, token: str) -> bytes:
        data = self._post("decrypt", {"ciphertext": token})
        return base64.b64decode(data["plaintext"])


def build_key_provider() -> KeyProvider:
    """Construct the KeyProvider selected by ``MANTLE_KEK_PROVIDER`` (default ``local``).

    Raises if the selected provider can't be constructed — the oracle wiring treats
    that as "no search" (503), never a silent plaintext fallback.
    """
    kind = (os.getenv("MANTLE_KEK_PROVIDER", "local") or "local").strip().lower()

    if kind == "local":
        from cryptography.fernet import Fernet
        from kernel.key_manager import get_encryption_key
        return LocalKeyProvider(Fernet(get_encryption_key()))

    if kind == "kms":
        return AwsKmsKeyProvider(os.getenv("MANTLE_KMS_KEY_ID", ""))

    if kind == "vault":
        return VaultTransitKeyProvider(
            os.getenv("VAULT_ADDR", ""),
            os.getenv("VAULT_TOKEN", ""),
            os.getenv("MANTLE_VAULT_TRANSIT_KEY", ""),
        )

    raise ValueError(f"Unknown MANTLE_KEK_PROVIDER: {kind!r} (expected local | kms | vault)")
