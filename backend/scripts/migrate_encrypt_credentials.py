#!/usr/bin/env python3
"""
Migration Script: Encrypt Existing Credentials
Encrypts all plaintext credentials in the database

Usage:
    python scripts/migrate_encrypt_credentials.py [--dry-run]

Options:
    --dry-run    Show what would be encrypted without making changes
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.encryption import get_encryption_service, is_encrypted
from app.models.data_connector import DataConnector
from app.models.llm_configuration import LLMConfiguration

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CredentialMigration:
    """Handles migration of credentials to encrypted format"""

    def __init__(self, db: Session, dry_run: bool = False):
        self.db = db
        self.dry_run = dry_run
        self.encryption_service = get_encryption_service()
        self.stats = {
            'connectors_processed': 0,
            'connectors_encrypted': 0,
            'connectors_skipped': 0,
            'llm_configs_processed': 0,
            'llm_configs_encrypted': 0,
            'llm_configs_skipped': 0,
            'errors': 0
        }

    def migrate_data_connectors(self):
        """Migrate data connector credentials"""
        logger.info("🔍 Migrating Data Connector credentials...")

        try:
            connectors = self.db.query(DataConnector).all()
            logger.info(f"Found {len(connectors)} data connectors")

            for connector in connectors:
                self.stats['connectors_processed'] += 1

                try:
                    # Check if credentials exist
                    if not connector.credentials:
                        logger.debug(f"  Skipping connector {connector.id} - no credentials")
                        self.stats['connectors_skipped'] += 1
                        continue

                    # Check if already encrypted
                    if is_encrypted(connector.credentials):
                        logger.debug(f"  Skipping connector {connector.id} - already encrypted")
                        self.stats['connectors_skipped'] += 1
                        continue

                    # Encrypt credentials
                    if self.dry_run:
                        logger.info(f"  [DRY RUN] Would encrypt connector {connector.id}: {connector.name}")
                        self.stats['connectors_encrypted'] += 1
                    else:
                        encrypted = self.encryption_service.encrypt(connector.credentials)
                        connector.credentials = encrypted
                        self.db.commit()
                        logger.info(f"  ✅ Encrypted connector {connector.id}: {connector.name}")
                        self.stats['connectors_encrypted'] += 1

                except Exception as e:
                    logger.error(f"  ❌ Error encrypting connector {connector.id}: {e}")
                    self.stats['errors'] += 1
                    if not self.dry_run:
                        self.db.rollback()

        except Exception as e:
            logger.error(f"❌ Error migrating connectors: {e}")
            self.stats['errors'] += 1

    def migrate_llm_configurations(self):
        """Migrate LLM configuration API keys"""
        logger.info("🔍 Migrating LLM Configuration API keys...")

        try:
            configs = self.db.query(LLMConfiguration).all()
            logger.info(f"Found {len(configs)} LLM configurations")

            for config in configs:
                self.stats['llm_configs_processed'] += 1

                try:
                    # Check if API key exists
                    if not config.api_key:
                        logger.debug(f"  Skipping LLM config {config.id} - no API key")
                        self.stats['llm_configs_skipped'] += 1
                        continue

                    # Check if already encrypted
                    if is_encrypted(config.api_key):
                        logger.debug(f"  Skipping LLM config {config.id} - already encrypted")
                        self.stats['llm_configs_skipped'] += 1
                        continue

                    # Encrypt API key
                    if self.dry_run:
                        logger.info(f"  [DRY RUN] Would encrypt LLM config {config.id}: {config.name}")
                        self.stats['llm_configs_encrypted'] += 1
                    else:
                        encrypted = self.encryption_service.encrypt(config.api_key)
                        config.api_key = encrypted
                        self.db.commit()
                        logger.info(f"  ✅ Encrypted LLM config {config.id}: {config.name}")
                        self.stats['llm_configs_encrypted'] += 1

                except Exception as e:
                    logger.error(f"  ❌ Error encrypting LLM config {config.id}: {e}")
                    self.stats['errors'] += 1
                    if not self.dry_run:
                        self.db.rollback()

        except Exception as e:
            logger.error(f"❌ Error migrating LLM configurations: {e}")
            self.stats['errors'] += 1

    def print_summary(self):
        """Print migration summary"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 MIGRATION SUMMARY")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("Mode: DRY RUN (no changes made)")
        else:
            logger.info("Mode: LIVE (changes committed)")

        logger.info("\nData Connectors:")
        logger.info(f"  Processed: {self.stats['connectors_processed']}")
        logger.info(f"  Encrypted: {self.stats['connectors_encrypted']}")
        logger.info(f"  Skipped:   {self.stats['connectors_skipped']}")

        logger.info("\nLLM Configurations:")
        logger.info(f"  Processed: {self.stats['llm_configs_processed']}")
        logger.info(f"  Encrypted: {self.stats['llm_configs_encrypted']}")
        logger.info(f"  Skipped:   {self.stats['llm_configs_skipped']}")

        logger.info(f"\nErrors: {self.stats['errors']}")

        total_encrypted = (
            self.stats['connectors_encrypted'] +
            self.stats['llm_configs_encrypted']
        )

        if total_encrypted > 0:
            logger.info(f"\n✅ Total items encrypted: {total_encrypted}")
        else:
            logger.info("\n✅ No items needed encryption")

        if self.stats['errors'] > 0:
            logger.warning(f"\n⚠️  {self.stats['errors']} errors occurred")

        logger.info("=" * 60)

    def run(self):
        """Run the migration"""
        logger.info("🚀 Starting Credential Encryption Migration")

        if self.dry_run:
            logger.info("⚠️  DRY RUN MODE - No changes will be made\n")
        else:
            logger.info("⚠️  LIVE MODE - Changes will be committed\n")

        # Migrate data connectors
        self.migrate_data_connectors()

        # Migrate LLM configurations
        self.migrate_llm_configurations()

        # Print summary
        self.print_summary()

        if self.dry_run:
            logger.info("\n💡 Run without --dry-run to apply changes")

        return self.stats['errors'] == 0


def generate_encryption_key():
    """Generate a new encryption key"""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    print("\n" + "=" * 60)
    print("🔑 GENERATED ENCRYPTION KEY")
    print("=" * 60)
    print("\nAdd this to your .env file:")
    print(f"\nENCRYPTION_KEY={key}")
    print("\n⚠️  IMPORTANT:")
    print("  - Keep this key secure and backed up")
    print("  - Never commit it to version control")
    print("  - Losing this key means losing access to encrypted data")
    print("  - Use the same key across all environments")
    print("=" * 60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate existing credentials to encrypted format"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be encrypted without making changes'
    )
    parser.add_argument(
        '--generate-key',
        action='store_true',
        help='Generate a new encryption key'
    )

    args = parser.parse_args()

    # Generate key if requested
    if args.generate_key:
        generate_encryption_key()
        return 0

    # Check if encryption key is set
    from app.core.config import settings
    if not settings.ENCRYPTION_KEY:
        logger.error("\n❌ ENCRYPTION_KEY not set in environment")
        logger.error("\nOptions:")
        logger.error("  1. Run with --generate-key to generate a new key")
        logger.error("  2. Add ENCRYPTION_KEY to your .env file")
        logger.error("  3. Set ENCRYPTION_KEY environment variable")
        return 1

    # Create database session
    db = SessionLocal()

    try:
        # Run migration
        migration = CredentialMigration(db, dry_run=args.dry_run)
        success = migration.run()

        return 0 if success else 1

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Migration cancelled by user")
        return 1

    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
