"""
Add agricultural tag columns to datasets table (ticket #4).

region_id/crop_id stay resolvable even after the reference entry is
deactivated — historical tags never break.
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

COLUMNS = [
    ("region_id", "INTEGER REFERENCES agri_regions(id)"),
    ("crop_id", "INTEGER REFERENCES agri_crops(id)"),
    ("season", "VARCHAR(50)"),
    ("yield_column", "VARCHAR(255)"),
]

INDEXES = [
    ("ix_datasets_region_id", "CREATE INDEX IF NOT EXISTS ix_datasets_region_id ON datasets (region_id)"),
    ("ix_datasets_crop_id", "CREATE INDEX IF NOT EXISTS ix_datasets_crop_id ON datasets (crop_id)"),
]


def run_migration():
    """Add agri tag columns to datasets table"""

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        print("🔧 Adding agricultural tag columns to datasets table...")

        for name, definition in COLUMNS:
            try:
                cursor.execute(
                    f"ALTER TABLE datasets ADD COLUMN IF NOT EXISTS {name} {definition};"
                )
                print(f"✅ Added {name} column")
            except Exception as e:
                print(f"⚠️  {name} column: {e}")

        for name, statement in INDEXES:
            try:
                cursor.execute(statement + ";")
                print(f"✅ Ensured index {name}")
            except Exception as e:
                print(f"⚠️  index {name}: {e}")

        print("✅ Migration completed successfully!")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
