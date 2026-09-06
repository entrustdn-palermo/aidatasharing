#!/usr/bin/env python3
"""
Test Agent-Based Chat with PDF Dataset
Tests the new MindsDB agent architecture with a PDF file
"""

import requests
import json
import time
import sys
import os

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PDF_PATH = "/tmp/airfield_annual_review_2024.pdf"

def login_admin():
    """Login as admin user"""
    print("🔐 Logging in as admin...")
    response = requests.post(
        f"{API_BASE_URL}/api/auth/login",
        data={
            "username": "admin@example.com",
            "password": "SuperAdmin123!"
        }
    )

    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✅ Login successful!")
        return token
    else:
        print(f"❌ Login failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

def upload_pdf(token):
    """Upload PDF file as dataset"""
    print(f"\n📤 Uploading PDF: {PDF_PATH}")

    # Check if file exists
    if not os.path.exists(PDF_PATH):
        print(f"❌ File not found: {PDF_PATH}")
        sys.exit(1)

    # Upload the file
    with open(PDF_PATH, "rb") as f:
        files = {
            "file": ("airfield_annual_review_2024.pdf", f, "application/pdf")
        }
        data = {
            "name": "Airfield Annual Review 2024",
            "description": "Annual review PDF document for testing agent-based chat"
        }
        headers = {
            "Authorization": f"Bearer {token}"
        }

        response = requests.post(
            f"{API_BASE_URL}/api/datasets/upload",
            files=files,
            data=data,
            headers=headers
        )

    if response.status_code in [200, 201]:
        result = response.json()
        print(f"✅ PDF uploaded successfully!")
        print(f"   Response: {json.dumps(result, indent=2)}")

        # Handle different response formats
        if isinstance(result, dict):
            dataset_id = result.get("id") or result.get("dataset_id") or result.get("dataset", {}).get("id")
            dataset_name = result.get("name") or result.get("dataset", {}).get("name")

            if dataset_id:
                print(f"   Dataset ID: {dataset_id}")
                print(f"   Dataset Name: {dataset_name}")
                return dataset_id

        print(f"❌ Could not extract dataset ID from response")
        sys.exit(1)
    else:
        print(f"❌ Upload failed: {response.status_code}")
        print(response.text)
        sys.exit(1)

def wait_for_agent_setup(token, dataset_id, max_wait=60):
    """Wait for agent to be set up for the dataset"""
    print(f"\n⏳ Waiting for agent setup (max {max_wait}s)...")

    headers = {"Authorization": f"Bearer {token}"}
    start_time = time.time()

    while time.time() - start_time < max_wait:
        response = requests.get(
            f"{API_BASE_URL}/api/datasets/{dataset_id}",
            headers=headers
        )

        if response.status_code == 200:
            dataset = response.json()
            agent_name = dataset.get("agent_name")

            if agent_name:
                print(f"✅ Agent created: {agent_name}")
                return True

            print(f"   Still waiting... ({int(time.time() - start_time)}s)")
            time.sleep(5)
        else:
            print(f"⚠️ Error checking dataset: {response.status_code}")

    print(f"⚠️ Agent setup timeout after {max_wait}s")
    return False

def chat_with_dataset(token, dataset_id, message):
    """Chat with dataset using agent-based architecture"""
    print(f"\n💬 Sending message: '{message}'")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "message": message,
        "stream": False
    }

    response = requests.post(
        f"{API_BASE_URL}/api/datasets/{dataset_id}/chat",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        result = response.json()
        print(f"\n✅ Response received!")
        print(f"{'='*80}")
        # MindsDB agent returns 'answer' field, not 'response'
        print(f"Response: {result.get('answer', result.get('response', 'No response'))}")
        print(f"{'='*80}")

        # Show additional info if available
        if result.get("agent_name"):
            print(f"\n📊 Agent Info:")
            print(f"   Agent: {result['agent_name']}")
            print(f"   Success: {result.get('success')}")
            print(f"   Response Time: {result.get('response_time', 'N/A')}")

        return result
    else:
        print(f"❌ Chat failed: {response.status_code}")
        print(response.text)
        return None

def test_multiple_questions(token, dataset_id):
    """Test multiple questions to verify agent context handling"""
    questions = [
        "What is this document about?",
        "What are the main highlights or achievements mentioned?",
        "Who are the key people or organizations mentioned?",
        "Summarize the financial information if any is present"
    ]

    print(f"\n{'='*80}")
    print(f"🧪 Testing Multiple Questions (Agent Context Handling)")
    print(f"{'='*80}")

    results = []
    for i, question in enumerate(questions, 1):
        print(f"\n--- Question {i}/{len(questions)} ---")
        result = chat_with_dataset(token, dataset_id, question)
        if result:
            results.append(result)
        time.sleep(2)  # Brief pause between questions

    return results

def main():
    """Main test function"""
    print("="*80)
    print("🧪 Testing Agent-Based Chat with PDF Dataset")
    print("="*80)

    # Step 1: Login
    token = login_admin()

    # Step 2: Upload PDF
    dataset_id = upload_pdf(token)

    # Step 3: Wait for agent setup
    agent_ready = wait_for_agent_setup(token, dataset_id)

    if not agent_ready:
        print("\n⚠️ Continuing anyway - agent might be created on first chat...")

    # Step 4: Test chat with multiple questions
    results = test_multiple_questions(token, dataset_id)

    # Summary
    print(f"\n{'='*80}")
    print(f"📋 Test Summary")
    print(f"{'='*80}")
    print(f"✅ Dataset uploaded: ID {dataset_id}")
    print(f"✅ Questions asked: {len(results)}")
    print(f"✅ Successful responses: {sum(1 for r in results if r.get('success'))}")

    # Check if agent-based
    if results and results[0].get("agent_name"):
        print(f"✅ Agent-based architecture: CONFIRMED")
        print(f"   Agent name: {results[0]['agent_name']}")
    else:
        print(f"⚠️ Agent-based architecture: NOT CONFIRMED")

    print(f"\n{'='*80}")
    print(f"🎉 Test Complete!")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
