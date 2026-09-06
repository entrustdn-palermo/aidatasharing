"""
Allow dataset_models.dataset_id to be NULL (ticket #1, Stories 19/24).

The pooled crop-suitability classifier is trained over the whole
cross-organization pool and belongs to no single Dataset (ADR-0001),
so the FK column must accept NULL. Existing rows are unaffected.

Run:  python migrations/allow_null_dataset_model_dataset_id.py
"""
import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

STATEMENTS = [
    "ALTER TABLE dataset_models ALTER COLUMN dataset_id DROP NOT NULL",
]


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        return

    conn = psycopg2.connect(database_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        cursor = conn.cursor()
        print("🔧 Allowing NULL dataset_models.dataset_id ...")
        for stmt in STATEMENTS:
            try:
                cursor.execute(stmt + ";")
                print(f"✅ {stmt}")
            except Exception as e:
                print(f"⚠️  {stmt}: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
