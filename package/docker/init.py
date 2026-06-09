"""
docker/init.py — Agience one-shot init container script.

Generates all cryptographic key material, data directories, and the
platform authority manifest before any other service starts. Runs on
every `docker compose up` but skips files that already exist — safe to
run repeatedly.

This is the ONLY place key material is ever written. The backend mounts
the keys directory and reads keys but never generates them.

Keypairs (Phase B/C of four-container-architecture.md):
- origin.private.pem / origin.public.pem    Origin service identity
- mantle.private.pem  / mantle.public.pem     Mantle service identity
- chorus.private.pem / chorus.public.pem    Chorus service identity

Each service reads only its own private key. All three public keys are
embedded inline in `authority.manifest.json`, which Mantle reads on first
boot and seeds as the singleton `vnd.agience.authority+json` artifact.

Bootstrap token: a fresh single-use token is generated and printed once.
Its bcrypt hash is written into the authority manifest. The token itself
is also written to `bootstrap.token` for capture by the operator. The
operator presents the cleartext token to `POST /auth/bootstrap/claim`,
which clears the hash from the authority artifact.
"""
import base64
import hashlib
import json
import os
import secrets
import string
import uuid
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DATA_DIR = Path("/data")
KEYS_DIR = DATA_DIR / "keys"

# Stable singleton UUID for the authority artifact (uuid5 of a fixed namespace
# + label so every deployment produces the same _key without coordination).
AUTHORITY_NAMESPACE = uuid.UUID("a91ec900-0000-4000-8000-000000000001")
AUTHORITY_ARTIFACT_ID = str(uuid.uuid5(AUTHORITY_NAMESPACE, "platform-authority"))

# Default service URIs — overridable via env at init time so federated /
# remote deployments can stamp real URLs into the manifest.
DEFAULT_ORIGIN_URI = os.getenv("AUTHORITY_ORIGIN_URI", "http://origin:8080")
DEFAULT_MANTLE_URI  = os.getenv("AUTHORITY_MANTLE_URI",  "http://mantle:8081")
DEFAULT_CHORUS_URI = os.getenv("AUTHORITY_CHORUS_URI", "http://chorus:8082")
DEFAULT_ISSUER     = os.getenv("AUTHORITY_ISSUER",     DEFAULT_ORIGIN_URI)


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def ensure_dirs() -> None:
    for d in ["keys", "minio", "arangodb", "arangodb-apps", "origin", "stream", "iris"]:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    os.chmod(KEYS_DIR, 0o711)  # 711: owner=rwx, group=x, others=x — containers can access files by name but can't list dir

    # Container UID ownership — these services run as non-root.
    # MinIO (UID 1000), ArangoDB (root)
    _chown_dir("minio", 1000, 1000)
    print("[init] Directories ready")


def _chown_dir(name: str, uid: int, gid: int) -> None:
    path = DATA_DIR / name
    try:
        os.chown(path, uid, gid)
    except OSError as exc:
        print(f"[init] Warning: could not chown {path}: {exc}")


def write_if_missing(path: Path, content: str, mode: int = 0o600) -> bool:
    if path.exists():
        print(f"[init] {path.name} already exists, skipping")
        return False
    path.write_text(content)
    os.chmod(path, mode)
    print(f"[init] Generated {path.name}")
    return True


def _gen_complex_password(length: int = 20) -> str:
    """Generate a password meeting common complexity requirements (upper, lower, digit, special)."""
    chars = string.ascii_letters + string.digits + "!@#$^&*"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(length))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$^&*" for c in pwd)
        ):
            return pwd


def gen_simple_secrets() -> None:
    write_if_missing(KEYS_DIR / "encryption.key", Fernet.generate_key().decode(), mode=0o400)
    write_if_missing(KEYS_DIR / "platform_internal.secret", secrets.token_urlsafe(48), mode=0o400)
    write_if_missing(KEYS_DIR / "inbound_nonce.secret", secrets.token_urlsafe(48), mode=0o400)
    # First-boot operator token — verified by Origin's /setup/complete endpoint.
    write_if_missing(KEYS_DIR / "setup.token", secrets.token_urlsafe(24), mode=0o400)
    # ArangoDB: use env override on first boot (import/existing-data scenario), else generate
    arango_pass = os.getenv("ARANGO_ROOT_PASSWORD") or _gen_complex_password()
    write_if_missing(KEYS_DIR / "arango.pass", arango_pass, mode=0o444)
    # MinIO password: use env override on first boot (import/existing-data scenario), else generate
    minio_pass = os.getenv("MINIO_ROOT_PASSWORD") or _gen_complex_password()
    write_if_missing(KEYS_DIR / "minio.pass", minio_pass, mode=0o444)


def _generate_rsa_keypair(label: str) -> rsa.RSAPrivateKey:
    """Generate an RSA-2048 keypair, write PEM files, return the private key for inline-JWKS export."""
    priv_path = KEYS_DIR / f"{label}.private.pem"
    pub_path  = KEYS_DIR / f"{label}.public.pem"
    if priv_path.exists() and pub_path.exists():
        print(f"[init] {label}.private.pem + {label}.public.pem already exist, skipping")
        return serialization.load_pem_private_key(priv_path.read_bytes(), password=None)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_text(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    )
    os.chmod(priv_path, 0o400)
    pub_path.write_text(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    )
    os.chmod(pub_path, 0o444)
    print(f"[init] Generated {label}.private.pem + {label}.public.pem")
    return private_key


def _public_key_to_jwk(public_key: rsa.RSAPublicKey, kid: str) -> dict:
    """Convert an RSA public key to a JWK (RFC 7517) entry."""
    numbers = public_key.public_numbers()
    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return {
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
        "n": b64url(n_bytes),
        "e": b64url(e_bytes),
    }


def gen_service_keypairs() -> dict:
    """Generate per-service keypairs (origin, mantle, chorus) and return them keyed by name.

    Each service holds only its own private key (filesystem perms enforce this; volume mounts
    project the right key into the right container). Public keys go into the authority manifest
    so service-to-service auth works without any HTTP fetch.
    """
    return {
        "origin": _generate_rsa_keypair("origin"),
        "mantle":  _generate_rsa_keypair("mantle"),
        "chorus": _generate_rsa_keypair("chorus"),
    }


def gen_authority_manifest(service_keys: dict) -> None:
    """Write `authority.manifest.json` to KEYS_DIR.

    Mantle reads this file on first boot and seeds it as the singleton
    `vnd.agience.authority+json` artifact in Arango. Idempotent: if the file already
    exists, the existing token hash is preserved (the operator may not have claimed yet).
    """
    manifest_path = KEYS_DIR / "authority.manifest.json"
    token_path    = KEYS_DIR / "bootstrap.token"

    if manifest_path.exists():
        print("[init] authority.manifest.json already exists, skipping")
        return

    # Generate the bootstrap token (single-use, claimed by first operator).
    bootstrap_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(bootstrap_token.encode()).hexdigest()
    # sha256 is used here (not bcrypt) so the manifest can be loaded without a runtime
    # password-hashing dependency in the init container. Origin's claim handler also uses
    # sha256 for verification — the token has 256 bits of entropy and lives only in operator
    # memory until claim, so the hash is solely about not storing the cleartext at rest.

    write_if_missing(token_path, bootstrap_token, mode=0o400)
    print("=" * 70)
    print("[init] BOOTSTRAP TOKEN (single-use, capture now):")
    print(f"       {bootstrap_token}")
    print("       Present this to POST /auth/bootstrap/claim to create the first operator.")
    print(f"       Also written to {token_path} (mode 0400).")
    print("=" * 70)

    manifest = {
        "artifact_id":      AUTHORITY_ARTIFACT_ID,
        "content_type":     "application/vnd.agience.authority+json",
        "schema_version":   1,
        "issuer":           DEFAULT_ISSUER,
        "trust_anchors": {
            "origin": {
                "uri": DEFAULT_ORIGIN_URI,
                "jwks": {"keys": [_public_key_to_jwk(service_keys["origin"].public_key(), "origin-1")]},
            },
            "mantle": {
                "uri": DEFAULT_MANTLE_URI,
                "jwks": {"keys": [_public_key_to_jwk(service_keys["mantle"].public_key(), "mantle-1")]},
            },
            "chorus": {
                "uri": DEFAULT_CHORUS_URI,
                "jwks": {"keys": [_public_key_to_jwk(service_keys["chorus"].public_key(), "chorus-1")]},
            },
        },
        "bootstrap_token_hash": token_hash,
    }

    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(manifest_path, 0o440)
    print(f"[init] Generated {manifest_path.name} (authority artifact id: {AUTHORITY_ARTIFACT_ID})")


def gen_licensing_keys() -> None:
    priv_path = KEYS_DIR / "licensing_private.pem"
    pub_path = KEYS_DIR / "licensing_public.pem"
    anchors_path = KEYS_DIR / "licensing_trust_anchors.json"

    if priv_path.exists() and pub_path.exists():
        print("[init] licensing keys already exist, skipping")
        if not anchors_path.exists():
            _write_trust_anchors(
                anchors_path,
                serialization.load_pem_public_key(pub_path.read_bytes()),
            )
        return

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    priv_path.write_text(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    )
    os.chmod(priv_path, 0o400)
    pub_path.write_text(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
    )
    os.chmod(pub_path, 0o444)
    _write_trust_anchors(anchors_path, public_key)
    print("[init] Generated licensing_private.pem + licensing_public.pem + licensing_trust_anchors.json")


def _write_trust_anchors(path: Path, public_key) -> None:
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    anchors = {
        "schema_version": "1",
        "keys": [{"kid": "lic-s1", "alg": "EdDSA", "public_key": b64url(pub_bytes)}],
    }
    path.write_text(json.dumps(anchors, indent=2) + "\n")
    os.chmod(path, 0o444)
    print("[init] Generated licensing_trust_anchors.json")


if __name__ == "__main__":
    sentinel = DATA_DIR / ".initialized"
    if sentinel.exists():
        print("[init] Already initialized, skipping")
        raise SystemExit(0)
    ensure_dirs()
    gen_simple_secrets()
    service_keys = gen_service_keypairs()
    gen_licensing_keys()
    gen_authority_manifest(service_keys)
    sentinel.write_text("")
    print("[init] Complete")
