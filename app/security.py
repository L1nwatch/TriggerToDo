import base64
import hashlib

from cryptography.fernet import Fernet


def derive_fernet_key(raw_secret: str) -> bytes:
    digest = hashlib.sha256(raw_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_str(raw_secret: str, plaintext: str) -> str:
    f = Fernet(derive_fernet_key(raw_secret))
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(raw_secret: str, ciphertext: str) -> str:
    f = Fernet(derive_fernet_key(raw_secret))
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
