#!/usr/bin/env python3
"""
Check database schema to see what tables and columns exist
"""
import os
import sys
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

def check_schema():
    """Check the database schema"""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in environment")
        sys.exit(1)

    # Connect to database
    print(f"🔗 Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected to database")
        print("\n" + "="*60)
        print("📊 Database Schema Information")
        print("="*60 + "\n")

        # Get all tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)

        tables = cursor.fetchall()
        print(f"📋 Tables found: {len(tables)}\n")

        for (table_name,) in tables:
            print(f"\n📦 Table: {table_name}")
            print("-" * 60)

            # Get columns for this table
            cursor.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))

            columns = cursor.fetchall()
            for col_name, data_type, is_nullable in columns:
                nullable = "NULL" if is_nullable == "YES" else "NOT NULL"
                print(f"  • {col_name}: {data_type} ({nullable})")

            # Get existing indexes for this table
            cursor.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND tablename = %s
                ORDER BY indexname;
            """, (table_name,))

            indexes = cursor.fetchall()
            if indexes:
                print(f"\n  📌 Existing indexes ({len(indexes)}):")
                for idx_name, idx_def in indexes:
                    print(f"    - {idx_name}")

        # Close connection
        cursor.close()
        conn.close()

        print("\n" + "="*60)
        print("✅ Schema check complete!")
        print("="*60)

    except psycopg2.Error as e:
        print(f"\n❌ ERROR: Database error occurred")
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: Unexpected error occurred")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    check_schema()
