#!/usr/bin/env python3
"""
Direct test of visualization loading from S3
"""
import sys
import os
import asyncio
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
env_path = Path('backend/.env')
load_dotenv(dotenv_path=env_path)

sys.path.insert(0, 'backend')

async def test_visualization_loading():
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.services.mindsdb import MindsDBService
    from app.core.config import settings

    db = SessionLocal()
    try:
        # Get a test dataset
        dataset = db.query(Dataset).filter(Dataset.id == 71).first()

        if not dataset:
            print("❌ Dataset 71 not found")
            return

        print(f"✓ Found dataset: {dataset.name}")
        print(f"  ID: {dataset.id}")
        print(f"  Is Multi-file: {dataset.is_multi_file_dataset}")
        print(f"  File Path: {dataset.file_path}")

        # Initialize MindsDB service
        mindsdb_service = MindsDBService()

        print("\n📥 Attempting to load dataset for visualization...")

        # Call the async method
        df = await mindsdb_service._load_dataset_for_visualization(dataset, db)

        if df is not None:
            print(f"✅ Successfully loaded DataFrame!")
            print(f"   Rows: {len(df)}")
            print(f"   Columns: {len(df.columns)}")
            print(f"   Column names: {list(df.columns)}")
            print(f"\n   First few rows:")
            print(df.head())
        else:
            print("❌ Failed to load DataFrame (returned None)")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_visualization_loading())
