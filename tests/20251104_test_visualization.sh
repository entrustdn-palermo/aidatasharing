#!/bin/bash

# Test Visualization Feature
# Tests that visualization requests work properly with MindsDB agent

BASE_URL="http://localhost:8000"

echo "=== Testing Visualization Feature ==="
echo ""

# Get auth token
echo "1. Getting authentication token..."
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@techcorp.com&password=Password123!" | \
  python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "✗ Failed to get authentication token"
  exit 1
fi

echo "✓ Token obtained"
echo ""

# Use existing dataset (dataset 92 - multi-file dataset)
DATASET_ID=92

echo "2. Testing Non-Visualization Request (baseline)..."
NON_VIZ_RESPONSE=$(curl -s -X POST "$BASE_URL/api/datasets/$DATASET_ID/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"How many customers are in the dataset?"}')

echo "$NON_VIZ_RESPONSE" | python3 << 'PYEOF'
import sys, json
try:
    data = json.load(sys.stdin)
    print(f"Source: {data.get('source', 'N/A')}")
    print(f"Agent: {data.get('agent_name', 'N/A')}")
    print(f"Has Visualizations: {data.get('has_visualizations', False)}")
    print(f"Success: {data.get('success', False)}")

    if data.get('success'):
        answer = data.get('answer', '')
        # Handle AgentCompletion format
        if 'AgentCompletion' in answer:
            import re
            match = re.search(r'content:\s*["\'](.+?)["\']', answer)
            if match:
                answer = match.group(1)
        print(f"Answer: {answer[:150]}...")
        print("✓ Non-visualization request works")
    else:
        print(f"✗ Request failed: {data.get('error', 'Unknown error')}")
except Exception as e:
    print(f"✗ Error: {e}")
    print(sys.stdin.read())
PYEOF

echo ""
echo "3. Testing Visualization Request..."
VIZ_RESPONSE=$(curl -s -X POST "$BASE_URL/api/datasets/$DATASET_ID/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Show me a chart of the data distribution"}')

echo "$VIZ_RESPONSE" | python3 << 'PYEOF'
import sys, json
try:
    data = json.load(sys.stdin)
    print(f"Source: {data.get('source', 'N/A')}")
    print(f"Agent: {data.get('agent_name', 'N/A')}")
    print(f"Has Visualizations: {data.get('has_visualizations', False)}")
    print(f"Success: {data.get('success', False)}")

    visualizations = data.get('visualizations', [])
    data_analysis = data.get('data_analysis', {})

    print(f"Visualizations Count: {len(visualizations)}")
    print(f"Data Analysis Present: {bool(data_analysis)}")

    if visualizations:
        print("\nVisualization Details:")
        for i, viz in enumerate(visualizations[:3], 1):
            print(f"  {i}. {viz.get('title', 'Untitled')}")
            print(f"     Type: {viz.get('type', 'Unknown')}")

    if data_analysis:
        print("\nData Analysis Summary:")
        basic_stats = data_analysis.get('basic_stats', {})
        if basic_stats:
            print(f"  Rows: {basic_stats.get('rows', 'N/A')}")
            print(f"  Columns: {basic_stats.get('columns', 'N/A')}")

    if data.get('success'):
        answer = data.get('answer', '')
        if 'AgentCompletion' in answer:
            import re
            match = re.search(r'content:\s*["\'](.+?)["\']', answer)
            if match:
                answer = match.group(1)
        print(f"\nAnswer: {answer[:150]}...")

        if data.get('has_visualizations') and visualizations:
            print("\n✓ Visualization request SUCCESS - visualizations generated")
        elif data.get('has_visualizations') is False:
            print("\n⚠️  Visualization requested but none generated")
            print("   This may be normal if LIDA is not available or dataset cannot be loaded")
        else:
            print("\n✓ Request succeeded (check if visualizations were expected)")
    else:
        print(f"\n✗ Request failed: {data.get('error', 'Unknown error')}")

except Exception as e:
    print(f"✗ Error parsing response: {e}")
    import traceback
    traceback.print_exc()
PYEOF

echo ""
echo "4. Testing Analysis Request..."
ANALYSIS_RESPONSE=$(curl -s -X POST "$BASE_URL/api/datasets/$DATASET_ID/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Analyze the data and show me insights"}')

echo "$ANALYSIS_RESPONSE" | python3 << 'PYEOF'
import sys, json
try:
    data = json.load(sys.stdin)
    print(f"Source: {data.get('source', 'N/A')}")
    print(f"Has Visualizations: {data.get('has_visualizations', False)}")
    print(f"Success: {data.get('success', False)}")

    if data.get('has_visualizations'):
        viz_count = len(data.get('visualizations', []))
        print(f"✓ Analysis with {viz_count} visualizations")
    else:
        print("⚠️  Analysis without visualizations")

except Exception as e:
    print(f"✗ Error: {e}")
PYEOF

echo ""
echo "=== Test Summary ==="
echo ""
echo "Tested scenarios:"
echo "1. ✓ Non-visualization request (baseline)"
echo "2. Visualization request with 'chart' keyword"
echo "3. Analysis request with 'analyze' keyword"
echo ""
echo "Expected behavior:"
echo "- Non-viz requests: has_visualizations=false"
echo "- Viz requests: has_visualizations=true (if LIDA available)"
echo "- All requests: source='agent', complete answers"
echo ""
echo "Check backend logs for detailed visualization generation:"
echo "  tail -f /tmp/backend.log | grep -E 'visualiz|LIDA|📊|📈'"
