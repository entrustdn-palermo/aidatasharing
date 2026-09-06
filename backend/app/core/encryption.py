"""
Encryption Service for Sensitive Data
Handles encryption and decryption of credentials, API keys, and other sensitive data
"""

import base64
import os
import logging
from typing import Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data"""

    def __init__(self):
        """Initialize encryption service with key from settings"""
        self._cipher = None
        self._initialize_cipher()

    def _initialize_cipher(self):
        """Initialize the Fernet cipher with key from settings"""
        try:
            # Get encryption key from settings
            encryption_key = getattr(settings, 'ENCRYPTION_KEY', None)

            if not encryption_key:
                # Generate a key if not provided (development only)
                logger.warning("ENCRYPTION_KEY not found in settings. Generating temporary key for development.")
                logger.warning("⚠️  This key will change on restart. Set ENCRYPTION_KEY in production!")
                encryption_key = Fernet.generate_key().decode()

            # Ensure key is bytes
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()

            # Validate key format
            if len(encryption_key) != 44 or not encryption_key.endswith(b'='):
                # Generate proper Fernet key from provided secret
                logger.info("Converting provided key to Fernet format")
                encryption_key = self._derive_fernet_key(encryption_key)

            self._cipher = Fernet(encryption_key)
            logger.info("✅ Encryption service initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize encryption service: {e}")
            raise ValueError(f"Failed to initialize encryption: {e}")

    def _derive_fernet_key(self, secret: bytes) -> bytes:
        """Derive a proper Fernet key from any secret using PBKDF2"""
        # Use a fixed salt (in production, store this securely)
        salt = b'aishare_platform_salt_v1'

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(secret))
        return key

    def encrypt(self, plaintext: Union[str, bytes]) -> str:
        """
        Encrypt plaintext data

        Args:
            plaintext: String or bytes to encrypt

        Returns:
            Encrypted string (base64 encoded)

        Raises:
            ValueError: If encryption fails
        """
        if not plaintext:
            return ""

        try:
            # Convert to bytes if string
            if isinstance(plaintext, str):
                plaintext = plaintext.encode('utf-8')

            # Encrypt
            encrypted = self._cipher.encrypt(plaintext)

            # Return as base64 string
            return encrypted.decode('utf-8')

        except Exception as e:
            logger.error(f"❌ Encryption failed: {e}")
            raise ValueError(f"Encryption failed: {e}")

    def decrypt(self, ciphertext: Union[str, bytes]) -> str:
        """
        Decrypt ciphertext data

        Args:
            ciphertext: Encrypted string (base64 encoded)

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails
        """
        if not ciphertext:
            return ""

        try:
            # Convert to bytes if string
            if isinstance(ciphertext, str):
                ciphertext = ciphertext.encode('utf-8')

            # Decrypt
            decrypted = self._cipher.decrypt(ciphertext)

            # Return as string
            return decrypted.decode('utf-8')

        except Exception as e:
            logger.error(f"❌ Decryption failed: {e}")
            raise ValueError(f"Decryption failed: {e}")

    def encrypt_dict(self, data: dict) -> str:
        """
        Encrypt a dictionary (useful for JSON credentials)

        Args:
            data: Dictionary to encrypt

        Returns:
            Encrypted JSON string
        """
        import json

        try:
            json_str = json.dumps(data)
            return self.encrypt(json_str)
        except Exception as e:
            logger.error(f"❌ Failed to encrypt dictionary: {e}")
            raise ValueError(f"Failed to encrypt dictionary: {e}")

    def decrypt_dict(self, ciphertext: str) -> dict:
        """
        Decrypt an encrypted dictionary

        Args:
            ciphertext: Encrypted JSON string

        Returns:
            Decrypted dictionary
        """
        import json

        try:
            json_str = self.decrypt(ciphertext)
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"❌ Failed to decrypt dictionary: {e}")
            raise ValueError(f"Failed to decrypt dictionary: {e}")

    def is_encrypted(self, data: str) -> bool:
        """
        Check if data appears to be encrypted

        Args:
            data: String to check

        Returns:
            True if data appears encrypted
        """
        if not data:
            return False

        try:
            # Fernet encrypted data starts with 'gAAAAA' in base64
            return data.startswith('gAAAAA') or data.startswith('gAAAAB')
        except:
            return False

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key

        Returns:
            Base64-encoded encryption key
        """
        return Fernet.generate_key().decode()


# Global encryption service instance
_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create the global encryption service instance

    Returns:
        EncryptionService instance
    """
    global _encryption_service

    if _encryption_service is None:
        _encryption_service = EncryptionService()

    return _encryption_service


# Convenience functions for quick access
def encrypt(plaintext: Union[str, bytes]) -> str:
    """Encrypt plaintext using global encryption service"""
    return get_encryption_service().encrypt(plaintext)


def decrypt(ciphertext: Union[str, bytes]) -> str:
    """Decrypt ciphertext using global encryption service"""
    return get_encryption_service().decrypt(ciphertext)


def encrypt_dict(data: dict) -> str:
    """Encrypt dictionary using global encryption service"""
    return get_encryption_service().encrypt_dict(data)


def decrypt_dict(ciphertext: str) -> dict:
    """Decrypt dictionary using global encryption service"""
    return get_encryption_service().decrypt_dict(ciphertext)


def is_encrypted(data: str) -> bool:
    """Check if data is encrypted using global encryption service"""
    return get_encryption_service().is_encrypted(data)
