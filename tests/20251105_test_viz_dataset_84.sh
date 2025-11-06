#!/bin/bash

# Test visualization with dataset 84 (has agent)
BASE_URL="http://localhost:8000"
DATASET_ID=84

echo "======================================================================="
echo "  Testing Visualization with Dataset $DATASET_ID"
echo "======================================================================="

# Get token
echo ""
echo "1. Getting authentication token..."
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@techcorp.com&password=Password123!" | \
  python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Failed to get token"
  exit 1
fi

echo "✅ Token obtained"

# Test visualization request
echo ""
echo "2. Testing visualization request..."
echo "   Message: 'Create visualizations of the data distribution'"
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/datasets/$DATASET_ID/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Create visualizations of the data distribution"}')

echo "$RESPONSE" | python3 << 'PYEOF'
import sys, json

try:
    data = json.load(sys.stdin)

    print("="*70)
    print("RESPONSE ANALYSIS")
    print("="*70)

    print(f"\n✓ Success: {data.get('success', False)}")
    print(f"✓ Source: {data.get('source', 'N/A')}")
    print(f"✓ Agent: {data.get('agent_name', 'N/A')}")
    print(f"✓ Has Visualizations: {data.get('has_visualizations', False)}")

    visualizations = data.get('visualizations', [])
    data_analysis = data.get('data_analysis', {})

    print(f"\n📊 Visualizations Count: {len(visualizations)}")
    print(f"📈 Data Analysis Present: {bool(data_analysis)}")

    if visualizations:
        print(f"\n{'='*70}")
        print("VISUALIZATIONS GENERATED")
        print('='*70)
        for i, viz in enumerate(visualizations, 1):
            print(f"\n{i}. {viz.get('title', 'Untitled')}")
            print(f"   Type: {viz.get('type', 'Unknown')}")
            desc = viz.get('description', '')
            if desc:
                print(f"   Description: {desc[:80]}...")

    if data_analysis:
        print(f"\n{'='*70}")
        print("DATA ANALYSIS")
        print('='*70)
        basic_stats = data_analysis.get('basic_stats', {})
        if basic_stats:
            print(f"\n✓ Rows: {basic_stats.get('rows', 'N/A')}")
            print(f"✓ Columns: {basic_stats.get('columns', 'N/A')}")

        recommendations = data_analysis.get('recommendations', [])
        if recommendations:
            print(f"\nRecommendations ({len(recommendations)}):")
            for rec in recommendations[:3]:
                print(f"  • {rec}")

    # Final verdict
    print(f"\n{'='*70}")
    if data.get('has_visualizations') and visualizations:
        print("RESULT: ✅ SUCCESS - Visualizations Generated!")
        print('='*70)
        print(f"\n🎉 {len(visualizations)} visualizations created successfully")
        print("   Frontend should be able to display these visualizations")
    elif data.get('source') == 'agent':
        print("RESULT: ⚠️  PARTIAL - Agent responded but no visualizations")
        print('='*70)
        print("\n   Agent is working but visualization generation didn't trigger")
        print("   Backend may need restart to pick up the fix")
    else:
        print("RESULT: ⚠️  NO VISUALIZATIONS")
        print('='*70)
        print("\n   No visualizations generated in this response")

except json.JSONDecodeError as e:
    print(f"❌ JSON Error: {e}")
    print("\nRaw response:")
    print(sys.stdin.read()[:500])
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
PYEOF

echo ""
