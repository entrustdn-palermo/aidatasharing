"""
Add agent-related columns to datasets table
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Add agent columns to datasets table"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        print("🔧 Adding agent-related columns to datasets table...")

        # Add agent_name column
        try:
            cursor.execute("""
                ALTER TABLE datasets
                ADD COLUMN IF NOT EXISTS agent_name VARCHAR;
            """)
            print("✅ Added agent_name column")
        except Exception as e:
            print(f"⚠️  agent_name column: {e}")

        # Add agent_created_at column
        try:
            cursor.execute("""
                ALTER TABLE datasets
                ADD COLUMN IF NOT EXISTS agent_created_at TIMESTAMP;
            """)
            print("✅ Added agent_created_at column")
        except Exception as e:
            print(f"⚠️  agent_created_at column: {e}")

        # Add agent_last_updated column
        try:
            cursor.execute("""
                ALTER TABLE datasets
                ADD COLUMN IF NOT EXISTS agent_last_updated TIMESTAMP;
            """)
            print("✅ Added agent_last_updated column")
        except Exception as e:
            print(f"⚠️  agent_last_updated column: {e}")

        # Add chat_model_provider column
        try:
            cursor.execute("""
                ALTER TABLE datasets
                ADD COLUMN IF NOT EXISTS chat_model_provider VARCHAR;
            """)
            print("✅ Added chat_model_provider column")
        except Exception as e:
            print(f"⚠️  chat_model_provider column: {e}")

        # Add chat_model_config column
        try:
            cursor.execute("""
                ALTER TABLE datasets
                ADD COLUMN IF NOT EXISTS chat_model_config JSON;
            """)
            print("✅ Added chat_model_config column")
        except Exception as e:
            print(f"⚠️  chat_model_config column: {e}")

        print("✅ Migration completed successfully!")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
