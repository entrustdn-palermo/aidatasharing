"""
Complete test for MindsDB agent creation with agriculture data
Tests:
1. Multi-file upload (2 CSV files - crops and farmers)
2. Agent creation on first chat
3. Agent stored in database
4. Agent exists in MindsDB
5. Agent reuse on subsequent chats
6. Cross-file SQL queries
"""
import requests
import json
import time
import os
import sys

# Change to backend directory for DB access
os.chdir('/Users/syaikhipin/Documents/program/simpleaisharing/backend')
sys.path.insert(0, '/Users/syaikhipin/Documents/program/simpleaisharing/backend')

from app.core.database import SessionLocal
from app.models.dataset import Dataset

BASE_URL = "http://localhost:8000"
ALICE_EMAIL = "alice@techcorp.com"
ALICE_PASSWORD = "Password123!"

# Agriculture test data
CROPS_CSV = """crop_id,crop_name,season,avg_yield_tons_per_ha,water_requirement_mm
1,Rice,Kharif,4.5,1200
2,Wheat,Rabi,3.2,450
3,Maize,Kharif,5.8,600
4,Cotton,Kharif,2.1,700
5,Sugarcane,Year-round,70.0,1800
6,Soybean,Kharif,1.8,500"""

FARMERS_CSV = """farmer_id,farmer_name,location,total_land_ha,crop_id,planted_ha,harvest_date
101,Rajesh Kumar,Punjab,10.5,2,8.0,2024-04-15
102,Priya Singh,Maharashtra,5.2,1,5.0,2024-10-20
103,Ahmed Khan,Gujarat,15.0,4,12.0,2024-11-10
104,Lakshmi Devi,Tamil Nadu,8.0,1,7.5,2024-09-25
105,Ramesh Patel,Karnataka,20.0,5,18.0,2024-12-01
106,Sunita Rao,Madhya Pradesh,12.0,3,11.0,2024-10-05"""

def check_dataset_in_db(dataset_id):
    """Check dataset details in database"""
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

def verify_agent_in_mindsdb(agent_name):
    """Verify agent exists in MindsDB using SDK"""
    try:
        import mindsdb_sdk
        server = mindsdb_sdk.connect('http://localhost:47334')

        # Try to get the agent
        agent = server.agents.get(agent_name)

        print(f"\n✅ Agent verified in MindsDB:")
        print(f"   Agent Name: {agent_name}")
        print(f"   Agent Object: {type(agent)}")

        return True
    except Exception as e:
        print(f"\n❌ Agent not found in MindsDB: {e}")
        return False

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

def upload_agriculture_data(token):
    """Upload 2 agriculture CSV files"""
    files = [
        ('files', ('crops.csv', CROPS_CSV, 'text/csv')),
        ('files', ('farmers.csv', FARMERS_CSV, 'text/csv'))
    ]

    data = {
        'name': 'Agriculture Dataset - India',
        'description': 'Crop and farmer data for agricultural analysis',
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
        print(f"\n✅ Agriculture dataset uploaded")
        print(f"   ID: {dataset['id']}")
        print(f"   Name: {dataset['name']}")
        print(f"   Files: {dataset['total_files_count']}")
        return dataset['id']
    else:
        print(f"❌ Upload failed: {response.text}")
        return None

def chat_with_dataset(token, dataset_id, message, chat_number):
    """Chat with dataset"""
    print(f"\n{'='*70}")
    print(f"CHAT #{chat_number}: {message}")
    print('='*70)

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
        print(f"   Model Type: {chat_response.get('model_type')}")
        print(f"\n📝 Answer Preview:")
        answer = chat_response.get('answer', '')
        print(f"   {answer[:300]}...")
        return chat_response
    else:
        print(f"❌ Chat failed: {response.text[:500]}")
        return None

def main():
    print("=" * 80)
    print("AGRICULTURE DATA - MINDSDB AGENT TEST")
    print("Testing: Multi-File Upload → Agent Creation → MindsDB Verification")
    print("=" * 80)

    # Step 1: Login
    print("\n[STEP 1] Logging in...")
    token = login()
    if not token:
        return

    # Step 2: Upload agriculture data
    print("\n[STEP 2] Uploading agriculture dataset (crops + farmers)...")
    dataset_id = upload_agriculture_data(token)
    if not dataset_id:
        return

    # Step 3: Check database BEFORE chat
    print("\n[STEP 3] Checking database BEFORE first chat...")
    db_state_before = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Dataset ID: {db_state_before['id']}")
    print(f"      Name: {db_state_before['name']}")
    print(f"      Agent Name: {db_state_before['agent_name']}")
    print(f"      Multi-file: {db_state_before['is_multi_file']}")
    print(f"      Files: {db_state_before['files_count']}")

    if db_state_before['agent_name']:
        print("   ⚠️  Agent exists before chat (unexpected!)")
    else:
        print("   ✅ Agent not created yet (correct - lazy creation)")

    # Wait for upload processing
    print("\n   ⏳ Waiting 3 seconds for upload processing...")
    time.sleep(3)

    # Step 4: FIRST CHAT - Should create agent
    print("\n[STEP 4] FIRST CHAT - Testing agent creation...")
    chat1 = chat_with_dataset(
        token,
        dataset_id,
        "How many crops are in the database? List their names and seasons.",
        1
    )

    # Step 5: Check database AFTER first chat
    print("\n[STEP 5] Checking database AFTER first chat...")
    time.sleep(3)  # Wait for agent creation
    db_state_after_chat1 = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Agent Name: {db_state_after_chat1['agent_name']}")
    print(f"      Agent Created: {db_state_after_chat1['agent_created_at']}")
    print(f"      Last Updated: {db_state_after_chat1['agent_last_updated']}")

    if db_state_after_chat1['agent_name']:
        print(f"   ✅ SUCCESS: Agent created with name: {db_state_after_chat1['agent_name']}")

        # Step 6: Verify agent in MindsDB
        print("\n[STEP 6] Verifying agent exists in MindsDB...")
        agent_exists = verify_agent_in_mindsdb(db_state_after_chat1['agent_name'])

        if agent_exists:
            print("   ✅ Agent successfully verified in MindsDB!")
        else:
            print("   ❌ Agent not found in MindsDB (but exists in DB)")
    else:
        print("   ❌ ERROR: Agent not created after first chat!")
        return

    # Step 7: SECOND CHAT - Should reuse agent
    print("\n[STEP 7] SECOND CHAT - Testing agent reuse...")
    chat2 = chat_with_dataset(
        token,
        dataset_id,
        "Which farmers are growing rice? Show farmer names and their planted hectares.",
        2
    )

    # Step 8: Check database after second chat
    print("\n[STEP 8] Checking database AFTER second chat...")
    time.sleep(2)
    db_state_after_chat2 = check_dataset_in_db(dataset_id)
    print(f"   📊 Database State:")
    print(f"      Agent Name: {db_state_after_chat2['agent_name']}")
    print(f"      Created: {db_state_after_chat2['agent_created_at']}")
    print(f"      Updated: {db_state_after_chat2['agent_last_updated']}")

    if db_state_after_chat1['agent_created_at'] == db_state_after_chat2['agent_created_at']:
        print("   ✅ Agent creation time unchanged - REUSED existing agent")
    else:
        print("   ⚠️  Agent creation time changed - may have been recreated")

    # Step 9: THIRD CHAT - Complex cross-file query
    print("\n[STEP 9] THIRD CHAT - Testing cross-file SQL query...")
    chat3 = chat_with_dataset(
        token,
        dataset_id,
        "Join the crops and farmers data: Show each farmer's name, what crop they're growing, the crop's water requirement, and calculate if they have enough land. This requires joining both tables.",
        3
    )

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"✅ Dataset ID: {dataset_id}")
    print(f"✅ Files uploaded: {db_state_before['files_count']} (crops.csv, farmers.csv)")
    print(f"✅ Owner: {ALICE_EMAIL}")
    print(f"✅ Agent created: {'Yes' if db_state_after_chat1['agent_name'] else 'No'}")
    print(f"✅ Agent name: {db_state_after_chat1['agent_name']}")
    print(f"✅ Agent in MindsDB: {agent_exists if 'agent_exists' in locals() else 'Not checked'}")
    print(f"✅ Agent reused: {'Yes' if db_state_after_chat1['agent_created_at'] == db_state_after_chat2['agent_created_at'] else 'No'}")
    print(f"✅ Multi-file context: {chat3.get('dataset_type') if chat3 else 'N/A'}")
    print(f"✅ Tables accessible: {chat3.get('tables_count') if chat3 else 'N/A'}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
