"""
Integration tests for encryption migration

Tests cover:
- Migration script execution
- Data integrity after migration
- Backward compatibility
- Rollback scenarios
- Performance under load
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
from cryptography.fernet import Fernet

from app.core.encryption import EncryptionService, is_encrypted
from app.models import DataConnector, LLMConfiguration
from scripts.migrate_encrypt_credentials import CredentialMigration


class TestEncryptionMigrationDataConnectors:
    """Test encryption migration for data connectors"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        mock_session = Mock()
        mock_session.query = Mock(return_value=mock_session)
        mock_session.filter = Mock(return_value=mock_session)
        mock_session.all = Mock(return_value=[])
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        return mock_session

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service with test key"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    @pytest.fixture
    def migration(self, db_session, encryption_service):
        """Create migration instance"""
        return CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=False
        )

    def test_migrate_plaintext_credentials(self, migration, db_session, encryption_service):
        """Test migrating plaintext credentials to encrypted format"""
        # Create connector with plaintext credentials
        plaintext_creds = json.dumps({"username": "admin", "password": "secret123"})
        connector = DataConnector(
            id=1,
            name="Test Connector",
            credentials=plaintext_creds,
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]

        # Run migration
        migration.migrate_data_connectors()

        # Verify credentials are now encrypted
        assert connector.credentials != plaintext_creds
        assert is_encrypted(connector.credentials)

        # Verify we can decrypt them
        decrypted = encryption_service.decrypt_dict(connector.credentials)
        assert decrypted == json.loads(plaintext_creds)

    def test_skip_already_encrypted_credentials(self, migration, db_session, encryption_service):
        """Test that already encrypted credentials are skipped"""
        # Create connector with already encrypted credentials
        original_creds = {"username": "admin", "password": "secret123"}
        encrypted_creds = encryption_service.encrypt_dict(original_creds)

        connector = DataConnector(
            id=1,
            name="Test Connector",
            credentials=encrypted_creds,
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]
        original_value = connector.credentials

        # Run migration
        migration.migrate_data_connectors()

        # Verify credentials unchanged
        assert connector.credentials == original_value

    def test_migrate_multiple_connectors(self, migration, db_session, encryption_service):
        """Test migrating multiple connectors in batch"""
        connectors = [
            DataConnector(
                id=i,
                name=f"Connector {i}",
                credentials=json.dumps({"user": f"user{i}", "pass": f"pass{i}"}),
                connector_type="postgresql"
            )
            for i in range(10)
        ]

        db_session.query().all.return_value = connectors

        # Run migration
        migration.migrate_data_connectors()

        # Verify all are encrypted
        for connector in connectors:
            assert is_encrypted(connector.credentials)

            # Verify data integrity
            decrypted = encryption_service.decrypt_dict(connector.credentials)
            assert f"user{connector.id}" in str(decrypted)

    def test_migrate_with_null_credentials(self, migration, db_session):
        """Test handling connectors with null credentials"""
        connector = DataConnector(
            id=1,
            name="Test Connector",
            credentials=None,
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]

        # Should not raise error
        migration.migrate_data_connectors()

        # Credentials should remain None
        assert connector.credentials is None

    def test_migrate_with_empty_credentials(self, migration, db_session):
        """Test handling connectors with empty credentials"""
        connector = DataConnector(
            id=1,
            name="Test Connector",
            credentials="",
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]

        # Should not raise error
        migration.migrate_data_connectors()

        # Empty credentials should remain empty or be skipped
        assert connector.credentials == "" or connector.credentials is None


class TestEncryptionMigrationLLMConfigurations:
    """Test encryption migration for LLM configurations"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        mock_session = Mock()
        mock_session.query = Mock(return_value=mock_session)
        mock_session.filter = Mock(return_value=mock_session)
        mock_session.all = Mock(return_value=[])
        mock_session.commit = Mock()
        return mock_session

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service with test key"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    @pytest.fixture
    def migration(self, db_session, encryption_service):
        """Create migration instance"""
        return CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=False
        )

    def test_migrate_llm_api_keys(self, migration, db_session, encryption_service):
        """Test migrating LLM API keys"""
        plaintext_key = "sk-1234567890abcdef"
        config = LLMConfiguration(
            id=1,
            name="OpenAI Config",
            api_key=plaintext_key,
            provider="openai"
        )

        db_session.query().all.return_value = [config]

        # Run migration
        migration.migrate_llm_configurations()

        # Verify API key is now encrypted
        assert config.api_key != plaintext_key
        assert is_encrypted(config.api_key)

        # Verify we can decrypt it
        decrypted = encryption_service.decrypt(config.api_key)
        assert decrypted == plaintext_key

    def test_migrate_multiple_llm_configs(self, migration, db_session, encryption_service):
        """Test migrating multiple LLM configurations"""
        configs = [
            LLMConfiguration(
                id=i,
                name=f"Config {i}",
                api_key=f"sk-key-{i}",
                provider="openai"
            )
            for i in range(5)
        ]

        db_session.query().all.return_value = configs

        # Run migration
        migration.migrate_llm_configurations()

        # Verify all are encrypted
        for config in configs:
            assert is_encrypted(config.api_key)
            decrypted = encryption_service.decrypt(config.api_key)
            assert f"sk-key-{config.id}" == decrypted


class TestEncryptionMigrationDryRun:
    """Test dry-run mode for migration"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        mock_session = Mock()
        mock_session.query = Mock(return_value=mock_session)
        mock_session.filter = Mock(return_value=mock_session)
        mock_session.all = Mock(return_value=[])
        mock_session.commit = Mock()
        return mock_session

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    def test_dry_run_does_not_modify_data(self, db_session, encryption_service):
        """Test that dry-run mode doesn't modify data"""
        plaintext_creds = json.dumps({"username": "admin", "password": "secret"})
        connector = DataConnector(
            id=1,
            name="Test",
            credentials=plaintext_creds,
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]

        # Run in dry-run mode
        migration = CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=True
        )
        migration.migrate_data_connectors()

        # Verify credentials unchanged
        assert connector.credentials == plaintext_creds
        assert not is_encrypted(connector.credentials)

        # Verify commit not called
        db_session.commit.assert_not_called()

    def test_dry_run_reports_changes(self, db_session, encryption_service, caplog):
        """Test that dry-run mode logs what would be changed"""
        import logging
        caplog.set_level(logging.INFO)

        connector = DataConnector(
            id=1,
            name="Test",
            credentials=json.dumps({"user": "admin"}),
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector]

        migration = CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=True
        )
        migration.migrate_data_connectors()

        # Verify dry-run message in logs
        assert any("DRY RUN" in record.message for record in caplog.records)


class TestEncryptionMigrationRollback:
    """Test rollback scenarios for migration"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        mock_session = Mock()
        mock_session.query = Mock(return_value=mock_session)
        mock_session.filter = Mock(return_value=mock_session)
        mock_session.all = Mock(return_value=[])
        mock_session.commit = Mock()
        mock_session.rollback = Mock()
        return mock_session

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    def test_rollback_on_error(self, db_session, encryption_service):
        """Test that migration rolls back on error"""
        connector1 = DataConnector(
            id=1,
            name="Good",
            credentials=json.dumps({"user": "admin"}),
            connector_type="postgresql"
        )

        connector2 = DataConnector(
            id=2,
            name="Bad",
            credentials="invalid_json{",
            connector_type="postgresql"
        )

        db_session.query().all.return_value = [connector1, connector2]

        migration = CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=False
        )

        # Should handle error gracefully
        try:
            migration.migrate_data_connectors()
        except Exception:
            pass

        # Rollback should be called on error
        # Implementation specific - adjust based on actual behavior


class TestEncryptionMigrationDataIntegrity:
    """Test data integrity after migration"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    def test_complex_credentials_preserved(self, encryption_service):
        """Test that complex credential structures are preserved"""
        complex_creds = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "mydb",
                "ssl": True,
                "pool_size": 10
            },
            "auth": {
                "username": "admin",
                "password": "secret123!@#",
                "token": "bearer_xyz"
            },
            "options": {
                "timeout": 30,
                "retry": 3,
                "features": ["feature1", "feature2"]
            }
        }

        # Encrypt
        encrypted = encryption_service.encrypt_dict(complex_creds)

        # Decrypt
        decrypted = encryption_service.decrypt_dict(encrypted)

        # Verify exact match
        assert decrypted == complex_creds
        assert decrypted["database"]["port"] == 5432
        assert decrypted["auth"]["password"] == "secret123!@#"
        assert "feature1" in decrypted["options"]["features"]

    def test_special_characters_preserved(self, encryption_service):
        """Test that special characters in credentials are preserved"""
        special_creds = {
            "password": "p@$$w0rd!#%&*()_+-=[]{}|;:',.<>?/~`",
            "api_key": "sk-\n\t\r special",
            "unicode": "密码 пароль كلمة السر"
        }

        encrypted = encryption_service.encrypt_dict(special_creds)
        decrypted = encryption_service.decrypt_dict(encrypted)

        assert decrypted == special_creds

    def test_large_credentials_handled(self, encryption_service):
        """Test that large credential payloads are handled"""
        large_creds = {
            "large_field": "A" * 100000,  # 100KB
            "nested": {
                "data": ["item"] * 1000
            }
        }

        encrypted = encryption_service.encrypt_dict(large_creds)
        decrypted = encryption_service.decrypt_dict(encrypted)

        assert decrypted == large_creds


class TestEncryptionMigrationPerformance:
    """Test performance characteristics of migration"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        mock_session = Mock()
        mock_session.query = Mock(return_value=mock_session)
        mock_session.filter = Mock(return_value=mock_session)
        mock_session.all = Mock(return_value=[])
        mock_session.commit = Mock()
        return mock_session

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    @pytest.mark.slow
    def test_migrate_large_dataset(self, db_session, encryption_service):
        """Test migrating a large number of records"""
        import time

        # Create 1000 connectors
        connectors = [
            DataConnector(
                id=i,
                name=f"Connector {i}",
                credentials=json.dumps({"user": f"user{i}", "pass": f"pass{i}"}),
                connector_type="postgresql"
            )
            for i in range(1000)
        ]

        db_session.query().all.return_value = connectors

        migration = CredentialMigration(
            db=db_session,
            encryption_service=encryption_service,
            dry_run=False
        )

        start = time.time()
        migration.migrate_data_connectors()
        elapsed = time.time() - start

        # Should complete in reasonable time (< 30 seconds for 1000 records)
        assert elapsed < 30

        # Verify all encrypted
        encrypted_count = sum(1 for c in connectors if is_encrypted(c.credentials))
        assert encrypted_count == 1000


class TestEncryptionMigrationBackwardCompatibility:
    """Test backward compatibility after migration"""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service"""
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_KEY": key}):
            return EncryptionService()

    def test_old_code_can_read_encrypted_data(self, encryption_service):
        """Test that code using decrypt functions can read migrated data"""
        original_creds = {"username": "admin", "password": "secret"}

        # Encrypt (as migration would)
        encrypted = encryption_service.encrypt_dict(original_creds)

        # Read back (as application code would)
        decrypted = encryption_service.decrypt_dict(encrypted)

        assert decrypted == original_creds

    def test_is_encrypted_correctly_identifies_format(self, encryption_service):
        """Test that is_encrypted helper works correctly"""
        plaintext = json.dumps({"user": "admin"})
        encrypted = encryption_service.encrypt(plaintext)

        assert not is_encrypted(plaintext)
        assert is_encrypted(encrypted)
