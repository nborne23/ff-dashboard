"""Fernet encrypt/decrypt for tokens and cookies at rest.

`GRIDIRON_SECRET_KEY` is an arbitrary user-provided secret string, not necessarily a
Fernet-format key (32 url-safe base64-encoded bytes). `derive_fernet_key` maps any
secret string to a valid Fernet key via SHA-256, so users can generate the secret
however they like (e.g. `openssl rand -hex 32`) instead of being forced to run
`Fernet.generate_key()`.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.gridiron.errors import CredentialDecryptError


def derive_fernet_key(secret_key: str) -> bytes:
    """Derive a valid Fernet key (url-safe base64, 32 bytes) from an arbitrary secret string."""
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(secret_key: str, plaintext: str) -> str:
    """Encrypt `plaintext`, returning a Fernet token (ASCII string) safe to store as TEXT."""
    fernet = Fernet(derive_fernet_key(secret_key))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(secret_key: str, token: str) -> str:
    """Decrypt a Fernet token produced by `encrypt`.

    Raises `CredentialDecryptError` if `secret_key` doesn't match the key the token was
    encrypted with, or if `token` is malformed/corrupt.
    """
    fernet = Fernet(derive_fernet_key(secret_key))
    try:
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CredentialDecryptError("failed to decrypt stored credential") from exc
