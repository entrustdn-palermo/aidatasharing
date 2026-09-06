#!/bin/bash

# Multi-file Download Testing Script
# Tests ZIP download and individual file download functionality

BASE_URL="http://localhost:8000"

echo "=== Multi-File Download Test Script ==="
echo ""

# Step 1: Register test user
echo "1. Registering test user..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123!","full_name":"Test User"}')

if echo "$REGISTER_RESPONSE" | grep -q "Email already registered"; then
  echo "   ✓ User already exists"
elif echo "$REGISTER_RESPONSE" | grep -q "id"; then
  echo "   ✓ User registered successfully"
else
  echo "   ✗ Failed to register: $REGISTER_RESPONSE"
fi

echo ""

# Step 2: Login
echo "2. Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=Test123!")

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "   ✗ Login failed: $LOGIN_RESPONSE"
  exit 1
fi

echo "   ✓ Logged in successfully"
echo "   Token: ${TOKEN:0:20}..."
echo ""

# Step 3: List datasets
echo "3. Listing datasets..."
DATASETS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/datasets" \
  -H "Authorization: Bearer $TOKEN")

echo "$DATASETS_RESPONSE" | python3 -m json.tool 2>/dev/null | head -50

# Get first dataset ID
DATASET_ID=$(echo "$DATASETS_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data[0]['id'] if isinstance(data, list) and len(data) > 0 else '')" 2>/dev/null)

if [ -z "$DATASET_ID" ]; then
  echo "   ⚠ No datasets found. Let's create a test multi-file dataset..."
  echo ""

  # Create test CSV files
  echo "4. Creating test CSV files..."
  mkdir -p /tmp/test_dataset

  cat > /tmp/test_dataset/file1.csv << 'EOF'
id,name,value
1,Apple,100
2,Banana,200
3,Cherry,300
EOF

  cat > /tmp/test_dataset/file2.csv << 'EOF'
id,category,price
1,Fruit,1.50
2,Fruit,0.75
3,Fruit,2.00
EOF

  echo "   ✓ Created file1.csv and file2.csv"
  echo ""

  # Upload multi-file dataset
  echo "5. Uploading multi-file dataset..."
  UPLOAD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/datasets/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "name=Test Multi-File Dataset" \
    -F "description=Testing multi-file download" \
    -F "files=@/tmp/test_dataset/file1.csv" \
    -F "files=@/tmp/test_dataset/file2.csv")

  echo "$UPLOAD_RESPONSE" | python3 -m json.tool 2>/dev/null

  DATASET_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

  if [ -z "$DATASET_ID" ]; then
    echo "   ✗ Failed to upload dataset"
    exit 1
  fi

  echo "   ✓ Dataset uploaded with ID: $DATASET_ID"
  echo ""
else
  echo "   ✓ Found dataset ID: $DATASET_ID"
  echo ""
fi

# Step 4: Get dataset details
echo "6. Getting dataset details..."
DATASET_DETAILS=$(curl -s -X GET "$BASE_URL/api/datasets/$DATASET_ID" \
  -H "Authorization: Bearer $TOKEN")

echo "$DATASET_DETAILS" | python3 -m json.tool 2>/dev/null

IS_MULTI_FILE=$(echo "$DATASET_DETAILS" | python3 -c "import sys, json; print(json.load(sys.stdin).get('is_multi_file', False))" 2>/dev/null)
FILES_COUNT=$(echo "$DATASET_DETAILS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data.get('files', [])))" 2>/dev/null)

echo ""
echo "   Dataset Type: $([ "$IS_MULTI_FILE" = "True" ] && echo "Multi-file ($FILES_COUNT files)" || echo "Single-file")"
echo ""

# Step 5: Test download-all endpoint
echo "7. Testing download-all endpoint..."
DOWNLOAD_URL="$BASE_URL/api/datasets/$DATASET_ID/download-all"
echo "   URL: $DOWNLOAD_URL"

curl -s -X GET "$DOWNLOAD_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -o "/tmp/dataset_${DATASET_ID}_download.zip" \
  -w "\n   HTTP Status: %{http_code}\n   Downloaded: %{size_download} bytes\n"

if [ -f "/tmp/dataset_${DATASET_ID}_download.zip" ]; then
  FILE_SIZE=$(wc -c < "/tmp/dataset_${DATASET_ID}_download.zip")
  if [ "$FILE_SIZE" -gt 0 ]; then
    echo "   ✓ File downloaded successfully"

    # Check if it's a ZIP file
    if file "/tmp/dataset_${DATASET_ID}_download.zip" | grep -q "Zip"; then
      echo "   ✓ File is a valid ZIP archive"
      echo ""
      echo "   ZIP Contents:"
      unzip -l "/tmp/dataset_${DATASET_ID}_download.zip" 2>/dev/null | tail -n +4
    else
      echo "   ℹ File is not a ZIP (likely single file download)"
      file "/tmp/dataset_${DATASET_ID}_download.zip"
    fi
  else
    echo "   ✗ Downloaded file is empty"
  fi
else
  echo "   ✗ Download failed"
fi

echo ""

# Step 6: Test individual file download (if multi-file)
if [ "$IS_MULTI_FILE" = "True" ] && [ "$FILES_COUNT" -gt 0 ]; then
  echo "8. Testing individual file download..."

  # Get first file ID
  FILE_ID=$(echo "$DATASET_DETAILS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['files'][0]['id'] if 'files' in data and len(data['files']) > 0 else '')" 2>/dev/null)
  FILE_NAME=$(echo "$DATASET_DETAILS" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['files'][0]['filename'] if 'files' in data and len(data['files']) > 0 else '')" 2>/dev/null)

  if [ -n "$FILE_ID" ]; then
    echo "   Testing download of file: $FILE_NAME (ID: $FILE_ID)"

    INDIVIDUAL_URL="$BASE_URL/api/datasets/$DATASET_ID/files/$FILE_ID/download"
    echo "   URL: $INDIVIDUAL_URL"

    curl -s -X GET "$INDIVIDUAL_URL" \
      -H "Authorization: Bearer $TOKEN" \
      -o "/tmp/individual_${FILE_NAME}" \
      -w "\n   HTTP Status: %{http_code}\n   Downloaded: %{size_download} bytes\n"

    if [ -f "/tmp/individual_${FILE_NAME}" ]; then
      FILE_SIZE=$(wc -c < "/tmp/individual_${FILE_NAME}")
      if [ "$FILE_SIZE" -gt 0 ]; then
        echo "   ✓ Individual file downloaded successfully"
        echo ""
        echo "   File content preview:"
        head -5 "/tmp/individual_${FILE_NAME}"
      else
        echo "   ✗ Downloaded file is empty"
      fi
    else
      echo "   ✗ Download failed"
    fi
  fi
fi

echo ""
echo "=== Test Complete ==="
echo ""
echo "Summary:"
echo "- Download-all endpoint: $([ -f "/tmp/dataset_${DATASET_ID}_download.zip" ] && echo "✓ Working" || echo "✗ Failed")"
if [ "$IS_MULTI_FILE" = "True" ]; then
  echo "- Individual file download: $([ -f "/tmp/individual_${FILE_NAME}" ] && echo "✓ Working" || echo "✗ Failed")"
fi
echo ""
echo "Downloaded files location:"
echo "- All files: /tmp/dataset_${DATASET_ID}_download.zip"
if [ "$IS_MULTI_FILE" = "True" ] && [ -n "$FILE_NAME" ]; then
  echo "- Individual: /tmp/individual_${FILE_NAME}"
fi
echo ""
