import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import get_settings

settings = get_settings()


class PasswordEncryption:
    """
    Encrypt NTNU passwords using AES-256 (Fernet).
    The encryption key is derived from a master key using PBKDF2.
    """

    _instance: "PasswordEncryption | None" = None
    _fernet: Fernet | None = None

    def __new__(cls) -> "PasswordEncryption":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._fernet is None:
            self._fernet = self._create_fernet()

    def _create_fernet(self) -> Fernet:
        """Create Fernet instance with derived key."""
        # Use a fixed salt derived from the encryption key itself
        # In production, consider storing salt per-user for better security
        salt = settings.encryption_key[:16].encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended minimum
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.encryption_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a plaintext password."""
        if self._fernet is None:
            raise RuntimeError("Encryption not initialized")
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt an encrypted password."""
        if self._fernet is None:
            raise RuntimeError("Encryption not initialized")
        return self._fernet.decrypt(ciphertext).decode()


def get_encryption() -> PasswordEncryption:
    """Get the password encryption singleton instance."""
    return PasswordEncryption()
