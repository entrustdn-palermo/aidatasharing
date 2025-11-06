#!/usr/bin/env python3
"""
End-to-end API test for visualization feature
Tests the actual API endpoint to verify visualizations are returned
"""
import requests
import json
import sys
import time

BASE_URL = "http://localhost:8000"

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def test_visualization_api():
    """Test the complete visualization API flow"""

    print_section("VISUALIZATION API TEST")

    # Step 1: Login
    print("\n1️⃣  Getting authentication token...")

    login_data = {
        "username": "alice@techcorp.com",
        "password": "Password123!"
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

        token = response.json().get("access_token")
        if not token:
            print("❌ No access token in response")
            return False

        print(f"✅ Token obtained: {token[:20]}...")

    except Exception as e:
        print(f"❌ Login error: {e}")
        return False

    # Step 2: Get a dataset to test with
    print("\n2️⃣  Finding a test dataset...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(f"{BASE_URL}/api/datasets/", headers=headers)

        if response.status_code != 200:
            print(f"❌ Failed to get datasets: {response.status_code}")
            return False

        datasets = response.json()
        if not datasets:
            print("❌ No datasets found")
            return False

        # Find a dataset (prefer multi-file)
        test_dataset = None
        for ds in datasets:
            if ds.get("is_multi_file_dataset"):
                test_dataset = ds
                break

        if not test_dataset:
            test_dataset = datasets[0]

        dataset_id = test_dataset["id"]
        dataset_name = test_dataset["name"]
        is_multi_file = test_dataset.get("is_multi_file_dataset", False)

        print(f"✅ Using dataset: {dataset_name} (ID: {dataset_id})")
        print(f"   Type: {'Multi-file' if is_multi_file else 'Single-file'}")

    except Exception as e:
        print(f"❌ Dataset fetch error: {e}")
        return False

    # Step 3: Test without visualization request (baseline)
    print("\n3️⃣  Testing baseline chat (no visualization keywords)...")

    try:
        chat_data = {
            "message": "How many rows are in the dataset?"
        }

        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/datasets/{dataset_id}/chat",
            json=chat_data,
            headers=headers
        )
        elapsed = time.time() - start_time

        if response.status_code != 200:
            print(f"❌ Chat failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

        result = response.json()

        print(f"✅ Chat successful ({elapsed:.2f}s)")
        print(f"   Source: {result.get('source', 'N/A')}")
        print(f"   Agent: {result.get('agent_name', 'N/A')}")
        print(f"   Has visualizations: {result.get('has_visualizations', False)}")

        if result.get('has_visualizations'):
            print(f"   ⚠️  Warning: Baseline request shouldn't have visualizations")

    except Exception as e:
        print(f"❌ Baseline chat error: {e}")
        return False

    # Step 4: Test WITH visualization request
    print("\n4️⃣  Testing visualization chat (WITH visualization keywords)...")

    try:
        chat_data = {
            "message": "Create visualizations showing the data distribution"
        }

        start_time = time.time()
        response = requests.post(
            f"{BASE_URL}/api/datasets/{dataset_id}/chat",
            json=chat_data,
            headers=headers
        )
        elapsed = time.time() - start_time

        if response.status_code != 200:
            print(f"❌ Visualization chat failed: {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return False

        result = response.json()

        print(f"✅ Chat successful ({elapsed:.2f}s)")
        print(f"   Source: {result.get('source', 'N/A')}")
        print(f"   Agent: {result.get('agent_name', 'N/A')}")
        print(f"   Has visualizations: {result.get('has_visualizations', False)}")

        # Check visualizations
        visualizations = result.get('visualizations', [])
        data_analysis = result.get('data_analysis', {})

        print(f"   Visualizations count: {len(visualizations)}")
        print(f"   Data analysis present: {bool(data_analysis)}")

        if len(visualizations) > 0:
            print(f"\n   📊 Visualization Details:")
            for i, viz in enumerate(visualizations[:5], 1):
                print(f"      {i}. {viz.get('title', 'Untitled')}")
                print(f"         Type: {viz.get('type', 'Unknown')}")
                if viz.get('description'):
                    desc = viz.get('description', '')[:60]
                    print(f"         Description: {desc}...")

        if data_analysis:
            print(f"\n   📈 Data Analysis:")
            basic_stats = data_analysis.get('basic_stats', {})
            if basic_stats:
                print(f"      Rows: {basic_stats.get('rows', 'N/A')}")
                print(f"      Columns: {basic_stats.get('columns', 'N/A')}")

            recommendations = data_analysis.get('recommendations', [])
            if recommendations:
                print(f"      Recommendations: {len(recommendations)}")

        # Determine success
        if result.get('has_visualizations') and len(visualizations) > 0:
            print(f"\n   ✅ VISUALIZATION TEST PASSED!")
            print(f"   ✅ Generated {len(visualizations)} visualizations successfully")
            return True
        else:
            print(f"\n   ⚠️  PARTIAL SUCCESS")
            print(f"   ⚠️  Response received but no visualizations generated")
            print(f"   ℹ️  This may be expected if:")
            print(f"      - Backend hasn't been restarted after the fix")
            print(f"      - LIDA is not installed")
            print(f"      - Dataset cannot be loaded for visualization")
            return False

    except Exception as e:
        print(f"❌ Visualization chat error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n🧪 Starting Visualization API Test")
    print(f"   Target: {BASE_URL}")

    success = test_visualization_api()

    print_section("TEST RESULT")

    if success:
        print("\n✅ ALL TESTS PASSED!")
        print("   Visualization feature is working correctly via API")
        print("   Frontend should be able to display visualizations")
        sys.exit(0)
    else:
        print("\n⚠️  TESTS INCOMPLETE")
        print("   Possible reasons:")
        print("   1. Backend needs to be restarted to pick up the fix")
        print("   2. Check backend logs for errors")
        print("   3. Verify S3/storage configuration")
        print("\n   Run the direct test to verify the fix:")
        print("   python3 test_viz_complete.py")
        sys.exit(1)
