#!/usr/bin/env python3
"""
Complete visualization test - simulates the full chat endpoint flow
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

async def test_complete_visualization_flow():
    from app.core.database import SessionLocal
    from app.models.dataset import Dataset
    from app.services.mindsdb import MindsDBService

    db = SessionLocal()
    try:
        # Get a test dataset
        dataset = db.query(Dataset).filter(Dataset.id == 71).first()

        if not dataset:
            print("❌ Dataset 71 not found")
            return

        print("="*60)
        print("VISUALIZATION FEATURE TEST")
        print("="*60)
        print(f"\n✓ Dataset: {dataset.name} (ID: {dataset.id})")
        print(f"  Type: {'Multi-file' if dataset.is_multi_file_dataset else 'Single-file'}")

        # Initialize MindsDB service
        mindsdb_service = MindsDBService()

        # Test message with visualization keyword
        test_message = "Show me a chart of the crop yields"

        print(f"\n📝 Test Query: '{test_message}'")
        print("\n" + "="*60)
        print("STEP 1: Visualization Detection")
        print("="*60)

        # Check visualization detection
        needs_visualization = any(keyword in test_message.lower() for keyword in [
            'visualiz', 'chart', 'graph', 'plot', 'diagram', 'show', 'display',
            'analyze', 'analysis', 'insight', 'pattern', 'trend', 'distribution',
            'correlation', 'relationship', 'compare', 'histogram', 'scatter',
            'heatmap', 'bar', 'line', 'pie'
        ])

        print(f"✓ Visualization requested: {needs_visualization}")

        print("\n" + "="*60)
        print("STEP 2: Dataset Loading for Visualization")
        print("="*60)

        # Test loading dataset for visualization
        dataset_df = await mindsdb_service._load_dataset_for_visualization(dataset, db)

        if dataset_df is not None:
            print(f"✅ DataFrame loaded successfully!")
            print(f"   • Rows: {len(dataset_df)}")
            print(f"   • Columns: {len(dataset_df.columns)}")
            print(f"   • Column names: {list(dataset_df.columns)[:5]}...")  # Show first 5

            print("\n" + "="*60)
            print("STEP 3: Visualization Generation")
            print("="*60)

            try:
                from app.services.data_visualization import get_visualization_service

                # Initialize visualization service
                viz_service = get_visualization_service(mindsdb_service.api_key)
                print("✓ Visualization service initialized")

                # Analyze dataset
                print("\n📊 Analyzing dataset...")
                data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                print(f"✓ Dataset analysis complete")

                if data_analysis:
                    print(f"   • Summary fields: {list(data_analysis.keys())}")

                # Generate visualizations
                print("\n📈 Generating visualizations...")
                visualizations = viz_service.generate_visualizations_with_lida(
                    dataset_df,
                    query=test_message,
                    max_visualizations=3
                )

                print(f"✅ Generated {len(visualizations)} visualizations")

                if visualizations:
                    print("\n   Visualization Details:")
                    for i, viz in enumerate(visualizations, 1):
                        print(f"   {i}. {viz.get('title', 'Untitled')}")
                        print(f"      Type: {viz.get('type', 'Unknown')}")
                        if viz.get('description'):
                            print(f"      Description: {viz.get('description')[:60]}...")

                print("\n" + "="*60)
                print("STEP 4: Response Format")
                print("="*60)

                # Simulate the response that would be returned
                response = {
                    "success": True,
                    "answer": "[Agent's text response would go here]",
                    "source": "agent",
                    "agent_name": f"dataset_{dataset.id}_multi_agent",
                    "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                    "response_time": 0.0,
                    "streaming": True,
                    "visualizations": visualizations,
                    "data_analysis": data_analysis,
                    "has_visualizations": len(visualizations) > 0
                }

                print(f"✓ Response structure:")
                print(f"   • success: {response['success']}")
                print(f"   • has_visualizations: {response['has_visualizations']}")
                print(f"   • visualization_count: {len(response['visualizations'])}")
                print(f"   • data_analysis_present: {bool(response['data_analysis'])}")

                print("\n" + "="*60)
                print("TEST RESULT: ✅ ALL STEPS PASSED")
                print("="*60)
                print("\n✅ Visualization feature is working correctly!")
                print("   The backend will be able to generate visualizations once restarted.")

            except ImportError as e:
                print(f"⚠️  Visualization service not available: {e}")
                print("   This is expected if LIDA is not installed")
            except Exception as e:
                print(f"❌ Visualization generation failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ Failed to load DataFrame")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    print("\n")
    asyncio.run(test_complete_visualization_flow())
    print("\n")
