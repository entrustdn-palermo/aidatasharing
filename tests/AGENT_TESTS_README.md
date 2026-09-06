# Agent-Based Architecture Tests

This directory contains test scripts for the MindsDB agent-based architecture implementation.

## Test Files

### test_agriculture_agent.py
Complete end-to-end test for multi-file agent creation with agriculture data.

**What it tests:**
- Multi-file dataset upload (crops.csv + farmers.csv)
- Agent creation on first chat
- Database traces (agent_name, agent_created_at)
- Agent reuse on subsequent chats
- Cross-file SQL queries
- MindsDB integration

**Run:**
```bash
cd /Users/syaikhipin/Documents/program/simpleaisharing
python tests/test_agriculture_agent.py
```

### test_agent_lifecycle.py
Tests the complete agent lifecycle from creation to deletion.

**What it tests:**
- Agent creation timing (lazy creation)
- Agent persistence across chats
- Database state verification
- MindsDB agent API integration

**Run:**
```bash
cd /Users/syaikhipin/Documents/program/simpleaisharing
python tests/test_agent_lifecycle.py
```

### test_multifile_upload.py
Tests multi-file upload functionality and file handling.

**What it tests:**
- Multiple file uploads in single dataset
- File metadata tracking
- FileUpload record creation
- S3 storage integration

**Run:**
```bash
cd /Users/syaikhipin/Documents/program/simpleaisharing
python tests/test_multifile_upload.py
```

### test_api.sh
Shell script for quick API endpoint testing.

**Run:**
```bash
cd /Users/syaikhipin/Documents/program/simpleaisharing
./tests/test_api.sh
```

## Prerequisites

1. **Backend running** on http://localhost:8000
2. **MindsDB running** on http://localhost:47334
3. **Test user credentials**:
   - Alice: alice@techcorp.com / Password123!
   - Bob: bob@innovateco.com / Password123!

## Test Data

The test scripts generate their own test CSV files:
- `crops.csv` - 6 crops with seasons and water requirements
- `farmers.csv` - 6 farmers with land holdings and crop assignments

## Expected Results

✅ All tests should pass with agent creation successful
✅ Agents should return actual data from CSV files
✅ Cross-file queries should work (joining crops + farmers)
✅ Files should appear in MindsDB files database

## Architecture Verified

These tests verify the complete agent-based architecture:
- File upload: S3 → MindsDB
- Agent creation: Single agent for multiple files
- Agent queries: MindsDB files database
- Agent reuse: Same agent across sessions
- File cleanup: MindsDB + S3 deletion on dataset delete
