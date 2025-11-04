"""
Test script to verify multi-file upload and MindsDB agent creation
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

# Test users
ALICE_EMAIL = "alice@techcorp.com"
BOB_EMAIL = "bob@dataanalytics.com"
TEST_PASSWORD = "testpass123"

def create_test_user(email, password, full_name):
    """Create a test user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/register-simple",
        json={"email": email, "password": password, "full_name": full_name}
    )
    print(f"Create user {email}: {response.status_code}")
    if response.status_code == 201:
        return response.json()
    return None

def login(email, password):
    """Login and get token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✅ Logged in as {email}")
        return token
    print(f"❌ Login failed for {email}: {response.json()}")
    return None

def upload_files(token, files_data, dataset_name):
    """Upload multiple files"""
    files = []
    for filename, content in files_data:
        files.append(('files', (filename, content, 'text/csv')))

    data = {
        'name': dataset_name,
        'description': f'Test multi-file dataset: {dataset_name}',
        'sharing_level': 'private'
    }

    response = requests.post(
        f"{BASE_URL}/api/datasets/upload",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"}
    )

    print(f"\nUpload status: {response.status_code}")
    if response.status_code == 200:
        response_data = response.json()
        # Extract dataset from response
        dataset = response_data.get('dataset', response_data)
        print(f"✅ Dataset created: ID={dataset['id']}, Name={dataset['name']}")
        print(f"   Multi-file: {dataset.get('is_multi_file_dataset')}")
        print(f"   Files count: {dataset.get('total_files_count')}")
        print(f"   Agent name: {dataset.get('agent_name')}")
        return dataset
    else:
        print(f"❌ Upload failed: {response.text}")
        return None

def chat_with_dataset(token, dataset_id, message):
    """Chat with dataset using agent"""
    response = requests.post(
        f"{BASE_URL}/api/datasets/{dataset_id}/chat",
        json={"message": message, "use_agents": True},
        headers={"Authorization": f"Bearer {token}"}
    )

    print(f"\nChat status: {response.status_code}")
    if response.status_code == 200:
        chat_response = response.json()
        print(f"✅ Chat response:")
        print(f"   Source: {chat_response.get('source')}")
        print(f"   Agent: {chat_response.get('agent_name')}")
        print(f"   Answer: {chat_response.get('answer', '')[:200]}...")
        return chat_response
    else:
        print(f"❌ Chat failed: {response.text}")
        return None

def test_mindsdb_agent_directly(dataset):
    """Test MindsDB agent using SDK directly"""
    try:
        import mindsdb_sdk

        print("\n=== Testing MindsDB SDK directly ===")

        # Connect to MindsDB
        server = mindsdb_sdk.connect('http://localhost:47334')
        print("✅ Connected to MindsDB")

        # Get the agent
        agent_name = dataset.get('agent_name')
        if not agent_name:
            print("❌ No agent_name in dataset")
            return

        print(f"Getting agent: {agent_name}")
        agent = server.agents.get(agent_name)
        print(f"✅ Retrieved agent: {agent_name}")

        # Test completion_stream
        print("\n🤖 Testing agent.completion_stream():")
        completion = agent.completion_stream([{
            'question': 'What data do you have? Summarize the tables.',
            'answer': None
        }])

        full_response = ""
        for chunk in completion:
            print(chunk, end='', flush=True)
            full_response += chunk

        print(f"\n✅ Streaming completed, total length: {len(full_response)}")

    except Exception as e:
        print(f"❌ MindsDB SDK test failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("=" * 60)
    print("Testing Multi-File Upload with MindsDB Agents")
    print("=" * 60)

    # Sample CSV data
    csv1_data = """name,age,city
Alice,30,New York
Bob,25,London
Charlie,35,Paris"""

    csv2_data = """product,price,stock
Laptop,999,50
Mouse,25,200
Keyboard,75,150"""

    csv3_data = """order_id,customer,product,quantity
1,Alice,Laptop,1
2,Bob,Mouse,2
3,Alice,Keyboard,1"""

    # Test with Alice
    print("\n" + "="*60)
    print("TESTING WITH ALICE")
    print("="*60)

    alice_token = login(ALICE_EMAIL, TEST_PASSWORD)
    if not alice_token:
        print("Creating Alice...")
        create_test_user(ALICE_EMAIL, TEST_PASSWORD, "Alice Smith")
        alice_token = login(ALICE_EMAIL, TEST_PASSWORD)

    if alice_token:
        alice_dataset = upload_files(
            alice_token,
            [
                ('customers.csv', csv1_data),
                ('products.csv', csv2_data),
                ('orders.csv', csv3_data)
            ],
            "Alice's Business Data"
        )

        if alice_dataset:
            # Wait a bit for processing
            print("\n⏳ Waiting 3 seconds for dataset processing...")
            time.sleep(3)

            # Chat with dataset
            chat_with_dataset(
                alice_token,
                alice_dataset['id'],
                "What is the average price of products?"
            )

            # Test MindsDB SDK directly
            test_mindsdb_agent_directly(alice_dataset)

    # Test with Bob
    print("\n" + "="*60)
    print("TESTING WITH BOB")
    print("="*60)

    bob_token = login(BOB_EMAIL, TEST_PASSWORD)
    if not bob_token:
        print("Creating Bob...")
        create_test_user(BOB_EMAIL, TEST_PASSWORD, "Bob Johnson")
        bob_token = login(BOB_EMAIL, TEST_PASSWORD)

    if bob_token:
        bob_dataset = upload_files(
            bob_token,
            [
                ('sales_jan.csv', csv2_data),
                ('sales_feb.csv', csv2_data)
            ],
            "Bob's Sales Data"
        )

        if bob_dataset:
            time.sleep(3)
            chat_with_dataset(
                bob_token,
                bob_dataset['id'],
                "How many products do we have in stock?"
            )

if __name__ == "__main__":
    main()
