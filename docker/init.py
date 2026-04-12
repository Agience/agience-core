"""
docker/init.py — Agience one-shot init container script.

Generates all cryptographic key material and data directories before any
other service starts. Runs on every `docker compose up` but skips files
that already exist — safe to run repeatedly.

This is the ONLY place key material is ever written. The backend mounts
the keys directory and reads keys but never generates them.
"""
import base64
import json
import os
import secrets
import string
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DATA_DIR = Path("/data")
KEYS_DIR = DATA_DIR / "keys"


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def ensure_dirs() -> None:
    for d in ["keys", "minio", "arangodb", "arangodb-apps", "postgresdb", "opensearch", "stream", "nexus"]:
        (DATA_DIR / d).mkdir(parents=True, exist_ok=True)
    os.chmod(KEYS_DIR, 0o711)  # 711: owner=rwx, group=x, others=x — containers can access files by name but can't list dir

    # Container UID ownership — these services run as non-root.
    # MinIO (UID 1000), OpenSearch (UID 1000), ArangoDB (root)
    _chown_dir("minio", 1000, 1000)
    _chown_dir("opensearch", 1000, 1000)
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
    write_if_missing(KEYS_DIR / "postgres.pass", secrets.token_urlsafe(32), mode=0o400)
    write_if_missing(KEYS_DIR / "encryption.key", Fernet.generate_key().decode(), mode=0o400)
    write_if_missing(KEYS_DIR / "platform_internal.secret", secrets.token_urlsafe(48), mode=0o400)
    write_if_missing(KEYS_DIR / "inbound_nonce.secret", secrets.token_urlsafe(48), mode=0o400)
    write_if_missing(KEYS_DIR / "setup.token", secrets.token_urlsafe(24), mode=0o400)
    write_if_missing(KEYS_DIR / "opensearch.pass", _gen_complex_password(), mode=0o444)
    # ArangoDB: use env override on first boot (import/existing-data scenario), else generate
    arango_pass = os.getenv("ARANGO_ROOT_PASSWORD") or _gen_complex_password()
    write_if_missing(KEYS_DIR / "arango.pass", arango_pass, mode=0o444)
    # MinIO password: use env override on first boot (import/existing-data scenario), else generate
    minio_pass = os.getenv("MINIO_ROOT_PASSWORD") or _gen_complex_password()
    write_if_missing(KEYS_DIR / "minio.pass", minio_pass, mode=0o444)


def gen_jwt_keys() -> None:
    priv_path = KEYS_DIR / "jwt_private.pem"
    pub_path = KEYS_DIR / "jwt_public.pem"
    if priv_path.exists() and pub_path.exists():
        print("[init] jwt_private.pem + jwt_public.pem already exist, skipping")
        return
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
    print("[init] Generated jwt_private.pem + jwt_public.pem")


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
    gen_jwt_keys()
    gen_licensing_keys()
    sentinel.write_text("")
    print("[init] Complete")
