#!/usr/bin/env python3
"""
Migration Script: Convert Existing Datasets to Agent-Based Architecture

This script creates MindsDB agents for all existing datasets that have AI chat enabled.
It supports both single-file and multi-file datasets.

Usage:
    python scripts/migrate_to_agents.py [--dry-run] [--limit N] [--dataset-id ID]

Options:
    --dry-run       Show what would be done without making changes
    --limit N       Limit migration to N datasets
    --dataset-id ID Migrate only specific dataset ID
    --verbose       Show detailed output
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.mindsdb import MindsDBService
from app.models.dataset import Dataset
from app.core.database import SessionLocal
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_datasets_to_agents(dry_run: bool = False, limit: int = None,
                               dataset_id: int = None, verbose: bool = False) -> dict:
    """
    Create agents for all existing datasets.

    Args:
        dry_run: If True, only show what would be done
        limit: Maximum number of datasets to migrate
        dataset_id: If provided, only migrate this specific dataset
        verbose: Show detailed output

    Returns:
        Dictionary with migration statistics
    """
    db = SessionLocal()
    mindsdb_service = MindsDBService()

    stats = {
        "total_datasets": 0,
        "migrated_successfully": 0,
        "already_migrated": 0,
        "failed": 0,
        "skipped": 0,
        "errors": []
    }

    try:
        # Build query
        query = db.query(Dataset).filter(
            Dataset.is_deleted == False,
            Dataset.ai_chat_enabled == True
        )

        if dataset_id:
            query = query.filter(Dataset.id == dataset_id)

        if limit:
            query = query.limit(limit)

        datasets = query.all()
        stats["total_datasets"] = len(datasets)

        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Found {len(datasets)} datasets to process")

        for idx, dataset in enumerate(datasets, 1):
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing {idx}/{len(datasets)}: {dataset.name} (ID: {dataset.id})")
            logger.info(f"Type: {'Multi-file' if dataset.is_multi_file_dataset else 'Single-file'}")

            try:
                # Check if already migrated
                if dataset.agent_name and dataset.agent_created_at:
                    logger.info(f"✅ Already has agent: {dataset.agent_name}")
                    stats["already_migrated"] += 1

                    # Verify agent exists in MindsDB
                    if not dry_run:
                        try:
                            agent = mindsdb_service.connection.agents.get(dataset.agent_name) if mindsdb_service._ensure_connection() else None
                            if agent:
                                logger.info(f"   Agent verified in MindsDB")
                            else:
                                logger.warning(f"   Agent NOT found in MindsDB, will recreate")
                                # Reset agent info to trigger recreation
                                dataset.agent_name = None
                                dataset.agent_created_at = None
                        except:
                            logger.warning(f"   Could not verify agent, assuming it needs recreation")
                            dataset.agent_name = None
                            dataset.agent_created_at = None

                    if dataset.agent_name:  # If still has agent name, skip
                        continue

                # Attempt migration
                if dry_run:
                    logger.info(f"[DRY RUN] Would create agent for: {dataset.name}")
                    stats["migrated_successfully"] += 1
                    continue

                # Create agent based on dataset type
                if dataset.is_multi_file_dataset:
                    logger.info(f"🔧 Creating MULTI-FILE agent...")
                    result = mindsdb_service.setup_multi_file_agent(dataset, db)
                else:
                    logger.info(f"🔧 Creating single-file agent...")
                    result = mindsdb_service.setup_single_file_agent(dataset, db)

                if result.get("success"):
                    agent_name = result["agent_name"]
                    tables_count = result.get("tables_count", result.get("files_count", 1))

                    logger.info(f"✅ Agent created successfully: {agent_name}")
                    logger.info(f"   Tables: {tables_count}")
                    logger.info(f"   Status: {result.get('status', 'created')}")

                    if verbose:
                        if "tables" in result:
                            logger.info(f"   Table references:")
                            for table in result["tables"]:
                                logger.info(f"     - {table}")

                    stats["migrated_successfully"] += 1
                else:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"❌ Failed to create agent: {error_msg}")
                    stats["failed"] += 1
                    stats["errors"].append({
                        "dataset_id": dataset.id,
                        "dataset_name": dataset.name,
                        "error": error_msg
                    })

            except Exception as e:
                logger.error(f"❌ Error processing dataset {dataset.id}: {e}")
                if verbose:
                    import traceback
                    logger.error(traceback.format_exc())
                stats["failed"] += 1
                stats["errors"].append({
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.name,
                    "error": str(e)
                })
                db.rollback()
                continue

    finally:
        db.close()

    return stats


def print_summary(stats: dict):
    """Print migration summary statistics."""
    logger.info(f"\n{'='*80}")
    logger.info("MIGRATION SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total datasets:          {stats['total_datasets']}")
    logger.info(f"Migrated successfully:   {stats['migrated_successfully']} ✅")
    logger.info(f"Already migrated:        {stats['already_migrated']} ♻️")
    logger.info(f"Failed:                  {stats['failed']} ❌")
    logger.info(f"Skipped:                 {stats['skipped']} ⏭️")

    if stats["errors"]:
        logger.info(f"\nErrors encountered:")
        for error in stats["errors"]:
            logger.info(f"  - Dataset {error['dataset_id']} ({error['dataset_name']}): {error['error']}")

    logger.info(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate existing datasets to agent-based architecture',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would happen
  python scripts/migrate_to_agents.py --dry-run

  # Migrate first 10 datasets
  python scripts/migrate_to_agents.py --limit 10

  # Migrate specific dataset
  python scripts/migrate_to_agents.py --dataset-id 123

  # Migrate all datasets with verbose output
  python scripts/migrate_to_agents.py --verbose
        """
    )

    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, metavar='N',
                       help='Limit migration to N datasets')
    parser.add_argument('--dataset-id', type=int, metavar='ID',
                       help='Migrate only specific dataset ID')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed output')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("🚀 Starting Dataset Migration to Agent-Based Architecture")
    logger.info(f"Dry run: {args.dry_run}")
    if args.limit:
        logger.info(f"Limit: {args.limit} datasets")
    if args.dataset_id:
        logger.info(f"Target dataset ID: {args.dataset_id}")

    try:
        stats = migrate_datasets_to_agents(
            dry_run=args.dry_run,
            limit=args.limit,
            dataset_id=args.dataset_id,
            verbose=args.verbose
        )

        print_summary(stats)

        # Exit with error code if any failures
        if stats["failed"] > 0:
            logger.warning("⚠️  Some datasets failed to migrate. Review errors above.")
            sys.exit(1)
        else:
            logger.info("✅ Migration completed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Migration failed with error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
