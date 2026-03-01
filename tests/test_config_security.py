from app.config import Settings
from app.security import decrypt_str, encrypt_str


def test_settings_normalizes_scopes_from_csv() -> None:
    settings = Settings(msal_scopes="Tasks.ReadWrite, offline_access , profile")
    assert settings.msal_scopes == ["Tasks.ReadWrite", "offline_access", "profile"]


def test_encrypt_decrypt_roundtrip() -> None:
    secret = "test-secret"
    plaintext = "token-cache-payload"

    encrypted = encrypt_str(secret, plaintext)
    assert encrypted != plaintext

    decrypted = decrypt_str(secret, encrypted)
    assert decrypted == plaintext
