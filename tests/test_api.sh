#!/bin/bash

echo "🧪 Testing API Connection..."
echo ""

# Test 1: Health Check
echo "1️⃣ Testing Health Endpoint..."
curl -s http://localhost:8000/health | jq '.status'
echo ""

# Test 2: Login
echo "2️⃣ Testing Login..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@example.com&password=admin123")

echo "$LOGIN_RESPONSE" | jq '.'
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
echo ""
echo "Token: ${TOKEN:0:20}..."
echo ""

# Test 3: Get Datasets with Token
echo "3️⃣ Testing Get Datasets..."
curl -s http://localhost:8000/api/datasets/ \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.[] | {id, name, type}'
echo ""

echo "✅ API Test Complete!"
