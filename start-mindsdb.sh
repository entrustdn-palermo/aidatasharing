#!/bin/bash

# Start MindsDB Server with Warning Suppression
echo "🚀 Starting MindsDB server..."

# Activate MindsDB environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mindsdb-server

# Set environment variables to suppress warnings
export PYTHONWARNINGS="ignore::UserWarning"
export PYDANTIC_DISABLE_PROTECTED_NAMESPACES="1"
export MINDSDB_CONFIG_PATH="/Users/syaikhipin/Documents/program/simpleaisharing/mindsdb_config.json"

# Change to project directory
cd /Users/syaikhipin/Documents/program/simpleaisharing

# Load S3 credentials used by MindsDB permanent storage
set -a
source backend/.env
set +a
export AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
export GOOGLE_API_KEY="$GOOGLE_API_KEY"
export AISHARE_PATCH_S3_GET_OBJECT_ATTRIBUTES="1"
export PYTHONPATH="/Users/syaikhipin/Documents/program/simpleaisharing${PYTHONPATH:+:$PYTHONPATH}"

# Start MindsDB with suppressed output for warnings and run in background
nohup python -m mindsdb --config="$MINDSDB_CONFIG_PATH" > /dev/null 2>&1 &
MINDSDB_PID=$!

# Wait a moment for startup
sleep 3

# Check if the process is still running
if kill -0 $MINDSDB_PID 2>/dev/null; then
    echo "✅ MindsDB server started with PID $MINDSDB_PID"
    echo "📊 GUI available at http://127.0.0.1:47334/"
    echo "🔧 To stop: kill $MINDSDB_PID"
    
    # Save PID for later reference
    echo $MINDSDB_PID > /tmp/mindsdb.pid
else
    echo "❌ MindsDB failed to start. Check the logs for details."
    exit 1
fi