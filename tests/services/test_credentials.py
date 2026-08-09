import pytest

from backend.gridiron.errors import CredentialDecryptError
from backend.gridiron.services import credentials


def test_encrypt_decrypt_round_trip() -> None:
    secret_key = "any-arbitrary-passphrase"
    token = credentials.encrypt(secret_key, "super-secret-token")

    assert credentials.decrypt(secret_key, token) == "super-secret-token"


def test_derive_fernet_key_accepts_non_fernet_secret() -> None:
    # Should not raise even though "hello" isn't a valid Fernet-format key.
    key = credentials.derive_fernet_key("hello")
    assert len(key) == 44  # url-safe base64 of 32 bytes


def test_decrypt_with_wrong_key_raises_typed_error() -> None:
    token = credentials.encrypt("key-one", "top-secret")

    with pytest.raises(CredentialDecryptError):
        credentials.decrypt("key-two", token)


def test_decrypt_malformed_token_raises_typed_error() -> None:
    with pytest.raises(CredentialDecryptError):
        credentials.decrypt("any-key", "not-a-valid-fernet-token")
