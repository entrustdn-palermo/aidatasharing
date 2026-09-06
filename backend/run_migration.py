#!/usr/bin/env python3
"""
Run database migration script
"""
import os
import sys
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

def run_migration():
    """Run the database migration to add performance indexes"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment")
        sys.exit(1)

    # Read migration SQL file
    migration_file = Path(__file__).parent / 'migrations' / 'add_performance_indexes_updated.sql'
    if not migration_file.exists():
        print(f"❌ ERROR: Migration file not found: {migration_file}")
        sys.exit(1)

    print(f"📄 Reading migration file: {migration_file}")
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    # Connect to database
    print(f"🔗 Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False  # Use transaction
        cursor = conn.cursor()

        print("✅ Connected to database")
        print("\n" + "="*60)
        print("🚀 Starting migration: add_performance_indexes.sql")
        print("="*60 + "\n")

        # Execute migration
        cursor.execute(migration_sql)

        # Get index creation count
        cursor.execute("""
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
        """)
        index_count = cursor.fetchone()[0]

        # Commit transaction
        conn.commit()

        print("\n" + "="*60)
        print("✅ Migration completed successfully!")
        print("="*60)
        print(f"\n📊 Total indexes created/verified: {index_count}")

        # Run ANALYZE to update statistics
        print("\n🔄 Running ANALYZE to update query planner statistics...")
        conn.autocommit = True
        cursor.execute("ANALYZE;")
        print("✅ ANALYZE completed")

        # Show some index stats
        print("\n📈 Index Statistics:")
        print("-" * 60)
        cursor.execute("""
            SELECT
                tablename,
                COUNT(*) as index_count
            FROM pg_indexes
            WHERE schemaname = 'public' AND indexname LIKE 'idx_%'
            GROUP BY tablename
            ORDER BY index_count DESC
            LIMIT 10;
        """)

        results = cursor.fetchall()
        for table, count in results:
            print(f"  • {table}: {count} indexes")

        # Close connection
        cursor.close()
        conn.close()

        print("\n" + "="*60)
        print("🎉 Migration process complete!")
        print("="*60)
        print("\n📝 Next steps:")
        print("  1. Monitor query performance for 24-48 hours")
        print("  2. Check slow query logs")
        print("  3. Verify application functionality")
        print("  4. Test key API endpoints with EXPLAIN ANALYZE")

    except psycopg2.Error as e:
        print(f"\n❌ ERROR: Database error occurred")
        print(f"Error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error occurred")
        print(f"Error: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
