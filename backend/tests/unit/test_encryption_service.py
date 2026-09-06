"""
Unit tests for EncryptionService

Tests cover:
- Basic encryption/decryption
- Dictionary encryption/decryption
- Error handling
- Edge cases
- Security requirements
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.encryption import (
    EncryptionService,
    encrypt,
    decrypt,
    encrypt_dict,
    decrypt_dict,
    is_encrypted,
)


class TestEncryptionService:
    """Test suite for EncryptionService class"""

    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key"""
        return Fernet.generate_key().decode()

    @pytest.fixture
    def service(self, encryption_key):
        """Create EncryptionService instance with test key.

        The service reads settings.ENCRYPTION_KEY (pydantic, loaded at import),
        so patch that attribute directly — patching os.environ has no effect.
        """
        with patch.object(settings, "ENCRYPTION_KEY", encryption_key):
            return EncryptionService()

    def test_initialization_success(self, encryption_key):
        """Test successful service initialization"""
        with patch.object(settings, "ENCRYPTION_KEY", encryption_key):
            service = EncryptionService()
            assert service._cipher is not None

    def test_initialization_no_key(self, caplog):
        """Without a configured key the service falls back to a generated
        temporary key (development convenience) and warns loudly."""
        with patch.object(settings, "ENCRYPTION_KEY", None):
            service = EncryptionService()
            assert service._cipher is not None
        assert any("ENCRYPTION_KEY not found" in record.message for record in caplog.records)

    def test_initialization_invalid_key(self):
        """A non-Fernet-format secret is derived into a valid key via PBKDF2
        rather than rejected."""
        with patch.object(settings, "ENCRYPTION_KEY", "invalid_key"):
            service = EncryptionService()
            assert service._cipher is not None
            assert service.decrypt(service.encrypt("probe")) == "probe"

    def test_encrypt_string(self, service):
        """Test encrypting a string"""
        plaintext = "secret_password_123"
        encrypted = service.encrypt(plaintext)

        assert encrypted is not None
        assert isinstance(encrypted, str)
        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)

    def test_decrypt_string(self, service):
        """Test decrypting a string"""
        plaintext = "secret_password_123"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_bytes(self, service):
        """Test encrypting bytes"""
        plaintext_bytes = b"secret_password_123"
        encrypted = service.encrypt(plaintext_bytes)

        assert encrypted is not None
        assert isinstance(encrypted, str)

    def test_decrypt_to_original_type(self, service):
        """Test decryption returns string"""
        plaintext = "secret_password_123"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert isinstance(decrypted, str)
        assert decrypted == plaintext

    def test_encrypt_decrypt_empty_string(self, service):
        """Test encrypting/decrypting empty string"""
        plaintext = ""
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_decrypt_unicode(self, service):
        """Test encrypting/decrypting Unicode characters"""
        plaintext = "Hello 世界 🔐 مرحبا"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_decrypt_long_text(self, service):
        """Test encrypting/decrypting long text"""
        plaintext = "A" * 10000
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_dict(self, service):
        """Test encrypting a dictionary"""
        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "sk-1234567890"
        }
        encrypted = service.encrypt_dict(data)

        assert encrypted is not None
        assert isinstance(encrypted, str)
        assert "username" not in encrypted  # Original keys should not be visible

    def test_decrypt_dict(self, service):
        """Test decrypting a dictionary"""
        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "sk-1234567890"
        }
        encrypted = service.encrypt_dict(data)
        decrypted = service.decrypt_dict(encrypted)

        assert decrypted == data

    def test_encrypt_decrypt_nested_dict(self, service):
        """Test encrypting/decrypting nested dictionary"""
        data = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "credentials": {
                    "username": "admin",
                    "password": "secret123"
                }
            },
            "api_keys": ["key1", "key2", "key3"]
        }
        encrypted = service.encrypt_dict(data)
        decrypted = service.decrypt_dict(encrypted)

        assert decrypted == data

    def test_encrypt_dict_empty(self, service):
        """Test encrypting empty dictionary"""
        data = {}
        encrypted = service.encrypt_dict(data)
        decrypted = service.decrypt_dict(encrypted)

        assert decrypted == data

    def test_decrypt_invalid_ciphertext(self, service):
        """Test decrypting invalid ciphertext raises error"""
        invalid_ciphertext = "not_valid_encrypted_text"
        with pytest.raises(Exception):
            service.decrypt(invalid_ciphertext)

    def test_decrypt_corrupted_data(self, service):
        """Test decrypting corrupted data raises error"""
        plaintext = "secret"
        encrypted = service.encrypt(plaintext)
        corrupted = encrypted[:-5] + "12345"  # Corrupt the end
        with pytest.raises(Exception):
            service.decrypt(corrupted)

    def test_decrypt_with_wrong_key(self, service):
        """Test decrypting with different key fails"""
        plaintext = "secret_password_123"
        encrypted = service.encrypt(plaintext)

        # Create new service with different key
        new_key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", new_key):
            wrong_service = EncryptionService()
            with pytest.raises(Exception):
                wrong_service.decrypt(encrypted)

    def test_encrypt_none_value(self, service):
        """Encrypting None returns empty string (falsy-input guard)."""
        assert service.encrypt(None) == ""

    def test_decrypt_none_value(self, service):
        """Decrypting None returns empty string (falsy-input guard)."""
        assert service.decrypt(None) == ""

    def test_is_encrypted_true(self, service):
        """Test is_encrypted identifies encrypted data"""
        plaintext = "secret"
        encrypted = service.encrypt(plaintext)

        assert is_encrypted(encrypted) is True

    def test_is_encrypted_false(self):
        """Test is_encrypted identifies plaintext data"""
        plaintext = "not_encrypted"

        assert is_encrypted(plaintext) is False

    def test_is_encrypted_empty_string(self):
        """Test is_encrypted handles empty string"""
        assert is_encrypted("") is False

    def test_is_encrypted_none(self):
        """Test is_encrypted handles None"""
        assert is_encrypted(None) is False

    def test_multiple_encryptions_different_ciphertext(self, service):
        """Test encrypting same plaintext produces different ciphertext (due to IV)"""
        plaintext = "secret"
        encrypted1 = service.encrypt(plaintext)
        encrypted2 = service.encrypt(plaintext)

        # Ciphertexts should be different (Fernet uses random IV)
        assert encrypted1 != encrypted2

        # But both should decrypt to same plaintext
        assert service.decrypt(encrypted1) == plaintext
        assert service.decrypt(encrypted2) == plaintext

    def test_encrypt_special_characters(self, service):
        """Test encrypting special characters"""
        plaintext = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_newlines_and_tabs(self, service):
        """Test encrypting text with newlines and tabs"""
        plaintext = "Line1\nLine2\tTabbed\rCarriageReturn"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_json_string(self, service):
        """Test encrypting JSON string"""
        json_data = json.dumps({"key": "value", "nested": {"data": 123}})
        encrypted = service.encrypt(json_data)
        decrypted = service.decrypt(encrypted)

        assert decrypted == json_data
        assert json.loads(decrypted) == json.loads(json_data)


class TestModuleLevelFunctions:
    """Test suite for module-level helper functions"""

    @pytest.fixture(autouse=True)
    def setup_encryption_key(self):
        """Set up encryption key for module-level functions"""
        self.key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", self.key):
            yield

    def test_encrypt_function(self):
        """Test module-level encrypt function"""
        plaintext = "secret"
        encrypted = encrypt(plaintext)

        assert encrypted is not None
        assert isinstance(encrypted, str)
        assert encrypted != plaintext

    def test_decrypt_function(self):
        """Test module-level decrypt function"""
        plaintext = "secret"
        encrypted = encrypt(plaintext)
        decrypted = decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_dict_function(self):
        """Test module-level encrypt_dict function"""
        data = {"username": "admin", "password": "secret"}
        encrypted = encrypt_dict(data)
        decrypted = decrypt_dict(encrypted)

        assert decrypted == data

    def test_is_encrypted_function(self):
        """Test module-level is_encrypted function"""
        plaintext = "secret"
        encrypted = encrypt(plaintext)

        assert is_encrypted(encrypted) is True
        assert is_encrypted(plaintext) is False


class TestSecurityRequirements:
    """Test suite for security requirements"""

    @pytest.fixture
    def service(self):
        """Create service with test key"""
        key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", key):
            return EncryptionService()

    def test_encryption_produces_non_deterministic_output(self, service):
        """Test that encryption is non-deterministic (uses IV)"""
        plaintext = "consistent_input"
        results = [service.encrypt(plaintext) for _ in range(10)]

        # All results should be different
        assert len(set(results)) == len(results)

        # But all should decrypt to same value
        for encrypted in results:
            assert service.decrypt(encrypted) == plaintext

    def test_encrypted_data_is_base64_encoded(self, service):
        """Test that encrypted data is valid base64"""
        import base64

        plaintext = "secret"
        encrypted = service.encrypt(plaintext)

        try:
            base64.urlsafe_b64decode(encrypted)
            is_valid_base64 = True
        except Exception:
            is_valid_base64 = False

        assert is_valid_base64

    def test_key_rotation_scenario(self):
        """Test scenario where key rotation is needed"""
        # Encrypt with old key
        old_key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", old_key):
            old_service = EncryptionService()
            encrypted = old_service.encrypt("secret_data")

        # Cannot decrypt with new key
        new_key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", new_key):
            new_service = EncryptionService()
            with pytest.raises(Exception):
                new_service.decrypt(encrypted)

        # Can still decrypt with old key
        with patch.object(settings, "ENCRYPTION_KEY", old_key):
            old_service = EncryptionService()
            decrypted = old_service.decrypt(encrypted)
            assert decrypted == "secret_data"

    def test_sensitive_data_not_logged(self, service, caplog):
        """Test that sensitive data is not logged"""
        import logging

        caplog.set_level(logging.DEBUG)

        plaintext = "super_secret_password"
        service.encrypt(plaintext)

        # Check that plaintext doesn't appear in logs
        for record in caplog.records:
            assert plaintext not in record.message

    def test_encryption_key_derivation(self):
        """Non-Fernet-format secrets are derived into valid keys via PBKDF2;
        an empty secret falls back to a generated development key."""
        secrets = [
            "short",
            "not_base64_!@#$",
            "a" * 100,
        ]

        for secret in secrets:
            with patch.object(settings, "ENCRYPTION_KEY", secret):
                service = EncryptionService()
                assert service._cipher is not None
                assert service.decrypt(service.encrypt("probe")) == "probe"

        with patch.object(settings, "ENCRYPTION_KEY", ""):
            service = EncryptionService()
            assert service._cipher is not None


class TestPerformance:
    """Test suite for performance characteristics"""

    @pytest.fixture
    def service(self):
        """Create service with test key"""
        key = Fernet.generate_key().decode()
        with patch.object(settings, "ENCRYPTION_KEY", key):
            return EncryptionService()

    def test_encrypt_large_payload(self, service):
        """Test encrypting large payload completes in reasonable time"""
        import time

        large_data = "A" * 1_000_000  # 1MB
        start = time.time()
        encrypted = service.encrypt(large_data)
        elapsed = time.time() - start

        assert encrypted is not None
        assert elapsed < 5.0  # Should complete in < 5 seconds

    def test_decrypt_large_payload(self, service):
        """Test decrypting large payload completes in reasonable time"""
        import time

        large_data = "A" * 1_000_000  # 1MB
        encrypted = service.encrypt(large_data)

        start = time.time()
        decrypted = service.decrypt(encrypted)
        elapsed = time.time() - start

        assert decrypted == large_data
        assert elapsed < 5.0  # Should complete in < 5 seconds

    def test_batch_encryption(self, service):
        """Test encrypting multiple values efficiently"""
        import time

        values = [f"secret_{i}" for i in range(100)]

        start = time.time()
        encrypted_values = [service.encrypt(v) for v in values]
        elapsed = time.time() - start

        assert len(encrypted_values) == 100
        assert elapsed < 5.0  # Should complete in < 5 seconds
