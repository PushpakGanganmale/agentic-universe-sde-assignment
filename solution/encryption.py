import hashlib
import hmac
import os
from pathlib import Path

from cryptography.fernet import Fernet


ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = ROOT / ".pii.key"


def load_key() -> bytes:
    """Load a persistent local encryption key or create one."""
    env_key = os.getenv("PII_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode("ascii")

    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()

    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    return key


_MASTER_KEY = load_key()
_CIPHER = Fernet(_MASTER_KEY)

# Derive a separate key for deterministic phone lookups.
_HMAC_KEY = hmac.new(
    _MASTER_KEY,
    b"agentic-universe-phone-lookup-v1",
    hashlib.sha256,
).digest()


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CIPHER.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _CIPHER.decrypt(value.encode("ascii")).decode("utf-8")


def phone_lookup_hash(canonical_phone: str) -> str:
    return hmac.new(
        _HMAC_KEY,
        canonical_phone.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
