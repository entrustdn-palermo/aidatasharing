"""
Test agent lifecycle:
1. Upload multi-file dataset
2. Check database - agent_name should be None
3. First chat - agent should be created
4. Check database - agent_name should be populated
5. Second chat - should reuse existing agent
6. Verify chat understands multi-file context
"""
import requests
import json
import time
import sys
import os

# Change to backend directory and add to path
os.chdir('/Users/syaikhipin/Documents/program/simpleaisharing/backend')
sys.path.insert(0, '/Users/syaikhipin/Documents/program/simpleaisharing/backend')

from app.core.database import SessionLocal
from app.models.dataset import Dataset

BASE_URL = "http://localhost:8000"
ALICE_EMAIL = "alice@techcorp.com"
ALICE_PASSWORD = "Password123!"

def check_dataset_in_db(dataset_id):
    """Check dataset agent_name in database"""
    db = SessionLocal()
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset:
        result = {
            'id': dataset.id,
            'name': dataset.name,
            'agent_name': dataset.agent_name,
            'agent_created_at': str(dataset.agent_created_at) if dataset.agent_created_at else None,
            'agent_last_updated': str(dataset.agent_last_updated) if dataset.agent_last_updated else None,
            'is_multi_file': dataset.is_multi_file_dataset,
            'files_count': dataset.total_files_count
        }
        db.close()
        return result
    db.close()
    return None

def login():
    """Login and get token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": ALICE_EMAIL, "password": ALICE_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✅ Logged in as {ALICE_EMAIL}")
        return token
    print(f"❌ Login failed: {response.json()}")
    return None

def upload_multi_file_dataset(token):
    """Upload 3 CSV files as one dataset"""

    # Three different CSV files with related data
    customers_csv = """id,name,email,city
1,Alice Smith,alice@email.com,New York
2,Bob Jones,bob@email.com,London
3,Charlie Brown,charlie@email.com,Paris"""

    products_csv = """product_id,product_name,price,category
101,Laptop,999,Electronics
102,Mouse,25,Electronics
103,Desk,450,Furniture"""

    orders_csv = """order_id,customer_id,product_id,quantity,order_date
1001,1,101,1,2024-01-15
1002,2,102,2,2024-01-16
1003,1,103,1,2024-01-17
1004,3,101,1,2024-01-18"""

    files = [
        ('files', ('customers.csv', customers_csv, 'text/csv')),
        ('files', ('products.csv', products_csv, 'text/csv')),
        ('files', ('orders.csv', orders_csv, 'text/csv'))
    ]

    data = {
        'name': 'Sales Database Multi-File',
        'description': 'Complete sales database with customers, products, and orders',
        'sharing_level': 'private'
    }

    response = requests.post(
        f"{BASE_URL}/api/datasets/upload",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        response_data = response.json()
        dataset = response_data.get('dataset', response_data)
        print(f"\n✅ Dataset uploaded successfully")
        print(f"   ID: {dataset['id']}")
        print(f"   Name: {dataset['name']}")
        print(f"   Multi-file: {dataset['is_multi_file_dataset']}")
        print(f"   Files: {dataset['total_files_count']}")
        return dataset['id']
    else:
        print(f"❌ Upload failed: {response.text}")
        return None

def chat_with_dataset(token, dataset_id, message, chat_number):
    """Chat with dataset"""
    print(f"\n{'='*60}")
    print(f"CHAT #{chat_number}: {message}")
    print('='*60)

    response = requests.post(
        f"{BASE_URL}/api/datasets/{dataset_id}/chat",
        json={"message": message, "use_agents": True},
        headers={"Authorization": f"Bearer {token}"}
    )

    if response.status_code == 200:
        chat_response = response.json()
        print(f"\n✅ Chat Response:")
        print(f"   Source: {chat_response.get('source')}")
        print(f"   Agent Name: {chat_response.get('agent_name')}")
        print(f"   Dataset Type: {chat_response.get('dataset_type')}")
        print(f"   Tables Count: {chat_response.get('tables_count')}")
        print(f"\n📝 Answer:")
        answer = chat_response.get('answer', '')
        # Print first 500 chars
        print(f"   {answer[:500]}...")
        return chat_response
    else:
        print(f"❌ Chat failed: {response.text}")
        return None

def main():
    print("="*70)
    print("AGENT LIFECYCLE TEST - Multi-File Context & Database Traces")
    print("="*70)

    # Step 1: Login
    print("\n[STEP 1] Logging in...")
    token = login()
    if not token:
        return

    # Step 2: Upload multi-file dataset
    print("\n[STEP 2] Uploading multi-file dataset...")
    dataset_id = upload_multi_file_dataset(token)
    if not dataset_id:
        return

    # Step 3: Check database BEFORE first chat
    print("\n[STEP 3] Checking database BEFORE first chat...")
    db_check_1 = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Dataset ID: {db_check_1['id']}")
    print(f"      Agent Name: {db_check_1['agent_name']}")
    print(f"      Agent Created At: {db_check_1['agent_created_at']}")
    print(f"      Multi-file: {db_check_1['is_multi_file']}")
    print(f"      Files Count: {db_check_1['files_count']}")

    if db_check_1['agent_name']:
        print("   ⚠️  WARNING: Agent already exists before chat!")
    else:
        print("   ✅ CORRECT: Agent not created yet (lazy creation)")

    # Wait a bit for upload processing
    print("\n   ⏳ Waiting 3 seconds for upload processing...")
    time.sleep(3)

    # Step 4: FIRST CHAT - Should create agent
    print("\n[STEP 4] FIRST CHAT (should create agent)...")
    chat1 = chat_with_dataset(
        token,
        dataset_id,
        "How many customers do we have? And what products are available?",
        1
    )

    # Step 5: Check database AFTER first chat
    print("\n[STEP 5] Checking database AFTER first chat...")
    time.sleep(2)  # Give it a moment to update
    db_check_2 = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Agent Name: {db_check_2['agent_name']}")
    print(f"      Agent Created At: {db_check_2['agent_created_at']}")
    print(f"      Agent Last Updated: {db_check_2['agent_last_updated']}")

    if db_check_2['agent_name']:
        print(f"   ✅ SUCCESS: Agent created: {db_check_2['agent_name']}")
    else:
        print("   ❌ ERROR: Agent still not created!")

    # Step 6: SECOND CHAT - Should reuse existing agent
    print("\n[STEP 6] SECOND CHAT (should reuse existing agent)...")
    time.sleep(1)
    chat2 = chat_with_dataset(
        token,
        dataset_id,
        "What is the total revenue from all orders? Show me customer names with their purchases.",
        2
    )

    # Step 7: Check database AFTER second chat
    print("\n[STEP 7] Checking database AFTER second chat...")
    time.sleep(1)
    db_check_3 = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Agent Name: {db_check_3['agent_name']}")
    print(f"      Agent Created At: {db_check_3['agent_created_at']}")
    print(f"      Agent Last Updated: {db_check_3['agent_last_updated']}")

    # Compare timestamps
    if db_check_2['agent_created_at'] == db_check_3['agent_created_at']:
        print("   ✅ SUCCESS: Agent creation time unchanged (reused existing agent)")
    else:
        print("   ⚠️  WARNING: Agent creation time changed (recreated?)")

    # Step 8: THIRD CHAT - Cross-file query to verify multi-file context
    print("\n[STEP 8] THIRD CHAT (cross-file query to test multi-file context)...")
    time.sleep(1)
    chat3 = chat_with_dataset(
        token,
        dataset_id,
        "Join the data: Show me each customer's name, what product they ordered, and the total price. This requires data from customers, orders, and products tables.",
        3
    )

    # Final Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"✅ Dataset uploaded: ID={dataset_id}, Files={db_check_1['files_count']}")
    print(f"✅ Agent lazy creation: {'Yes' if not db_check_1['agent_name'] else 'No'}")
    print(f"✅ Agent created on first chat: {'Yes' if db_check_2['agent_name'] else 'No'}")
    print(f"✅ Agent reused on second chat: {'Yes' if db_check_2['agent_created_at'] == db_check_3['agent_created_at'] else 'No'}")
    print(f"✅ Agent name: {db_check_3['agent_name']}")
    print(f"✅ Multi-file context: {chat3.get('dataset_type') if chat3 else 'N/A'}")
    print(f"✅ Tables accessible: {chat3.get('tables_count') if chat3 else 'N/A'}")

    # Check if MindsDB agent exists
    print("\n[BONUS] Verifying agent in MindsDB...")
    try:
        import mindsdb_sdk
        server = mindsdb_sdk.connect('http://localhost:47334')
        agent = server.agents.get(db_check_3['agent_name'])
        print(f"   ✅ Agent exists in MindsDB: {db_check_3['agent_name']}")
        print(f"   ✅ Agent is accessible and ready")
    except Exception as e:
        print(f"   ⚠️  Could not verify agent in MindsDB: {e}")

if __name__ == "__main__":
    main()
