# Pending Improvements and Issues

This document tracks identified issues and improvements needed for the AI Share Platform.

## High Priority Issues

### 1. Multi-File Dataset Download ✅ IMPLEMENTED (Nov 4, 2025)

**Issue**: When a dataset contains multiple files, only one file can be downloaded, not all files or individual files.

**Solution Implemented**:

**Backend Changes**:
1. Added `GET /api/datasets/{dataset_id}/download-all` endpoint ([datasets.py:1457-1593](backend/app/api/datasets.py#L1457-L1593))
   - Downloads all files as ZIP for multi-file datasets
   - Downloads single file directly for single-file datasets
   - Creates ZIP archive in memory using `zipfile` module
   - Handles permissions and access control

2. Added `GET /api/datasets/{dataset_id}/files/{file_id}/download` endpoint ([datasets.py:1595-1673](backend/app/api/datasets.py#L1595-L1673))
   - Downloads specific file from multi-file dataset
   - Validates file belongs to dataset
   - Checks user permissions

3. Added `get_file_content()` method to StorageService ([storage.py:470-472](backend/app/services/storage.py#L470-L472))
   - Retrieves file content as bytes for ZIP creation
   - Works with both S3 and local storage backends

**Frontend Changes**:
1. Added `handleDownloadAll()` function ([page.tsx:443-494](frontend/src/app/datasets/[id]/page.tsx#L443-L494))
   - Downloads all files as ZIP or single file
   - Handles blob download with proper filename

2. Added `handleDownloadFile()` function ([page.tsx:496-531](frontend/src/app/datasets/[id]/page.tsx#L496-L531))
   - Downloads individual files from multi-file dataset

3. Updated download button UI ([page.tsx:718-725](frontend/src/app/datasets/[id]/page.tsx#L718-L725))
   - Shows "Download All (X files)" for multi-file datasets
   - Shows "Download (TYPE)" for single-file datasets

4. Added "Dataset Files" section ([page.tsx:1253-1305](frontend/src/app/datasets/[id]/page.tsx#L1253-L1305))
   - Lists all files in multi-file dataset
   - Shows filename, size, and file type
   - Individual download button for each file
   - "Download All as ZIP" button at top

5. Updated Quick Actions sidebar ([page.tsx:1512-1528](frontend/src/app/datasets/[id]/page.tsx#L1512-L1528))
   - Context-aware download text for multi-file vs single-file

**Testing Required**:
- [ ] Upload multi-file dataset and verify all files appear in UI
- [ ] Test "Download All" button creates ZIP with all files
- [ ] Test individual file download buttons
- [ ] Test with single-file dataset (should download directly, not ZIP)
- [ ] Test with large files (memory handling)
- [ ] Test permissions (shared users can download if allowed)

**Priority**: ✅ COMPLETE - Ready for testing

---

### 2. Dataset Preview in Frontend ⚠️  NEEDS TESTING

**Issue**: Need to verify dataset preview works correctly for:
- Single-file datasets
- Multi-file datasets
- Web connector datasets (API)

**Test Cases**:
1. Upload single CSV - Preview should show data
2. Upload multiple CSVs - Preview should show all files or first file
3. Create API connector - Preview should work
4. Check if preview shows correct number of rows/columns

**Files to Check**:
- `frontend/src/app/datasets/[id]/page.tsx`
- Preview component rendering logic

**Priority**: MEDIUM - Feature exists but needs verification

---

### 3. Sharing Ownership Transfer ⚠️  NEEDS TESTING

**Issue**: Need to verify ownership transfer works correctly

**Test Cases**:
1. Alice creates dataset
2. Alice transfers ownership to Bob
3. Verify Bob becomes owner
4. Verify Alice loses owner permissions
5. Verify dataset still accessible

**API Endpoint**: `PUT /api/datasets/{id}/transfer-ownership`

**Priority**: MEDIUM - Core sharing feature

---

### 4. Sharing Page Functionality ⚠️  NEEDS TESTING

**Issue**: Need to verify sharing page works for all dataset types

**Test Cases**:
1. Create share link for uploaded file dataset
2. Create share link for multi-file dataset
3. Create share link for API connector dataset
4. Verify shared dataset is accessible via link
5. Verify permissions are enforced

**Files to Check**:
- `frontend/src/app/datasets/[id]/share/page.tsx`
- `backend/app/api/data_sharing.py`

**Priority**: MEDIUM - Core sharing feature

---

### 5. Web Connector (API) with Sharing ⚠️  NEEDS TESTING

**Issue**: Need to verify web connectors work with sharing system

**Test Cases**:
1. Create API connector dataset
2. Share the API connector dataset
3. Verify shared user can access data
4. Verify API data refreshes correctly
5. Test permissions on API datasets

**Priority**: MEDIUM - Integration feature

---

### 6. Chat with Agents on Shared Datasets ⚠️  NEEDS TESTING

**Issue**: Need to verify MindsDB agents work on shared datasets

**Test Cases**:
1. Alice creates multi-file dataset with agent
2. Alice shares dataset with Bob
3. Bob accesses shared dataset
4. Bob tries to chat with agent
5. Verify Bob can query the data through agent
6. Verify agent permissions are correct

**Expected Behavior**:
- Shared users should be able to chat if `enable_chat` is true
- Agent should work regardless of who is querying
- Data should be accessible through agent

**Files to Check**:
- `backend/app/api/datasets.py` - Chat endpoint permissions
- `backend/app/services/mindsdb.py` - Agent access control

**Priority**: MEDIUM-HIGH - Core feature for shared datasets

---

## Implementation Plan

### Phase 1: Critical Fixes (Week 1)
1. ✅ Fix multi-file download
   - Implement ZIP download for all files
   - Implement individual file download
   - Update frontend UI

### Phase 2: Testing & Verification (Week 1-2)
2. ⚠️  Test dataset preview
3. ⚠️  Test sharing ownership
4. ⚠️  Test sharing page
5. ⚠️  Test web connector sharing
6. ⚠️  Test agent chat on shared datasets

### Phase 3: Documentation (Week 2)
7. Document all sharing workflows
8. Create user guide for multi-file datasets
9. Update API documentation

---

## Testing Checklist

### Multi-File Datasets
- [ ] Upload multiple files
- [ ] Download all files as ZIP
- [ ] Download individual files
- [ ] Preview all files
- [ ] Chat with agent (all files accessible)
- [ ] Share dataset (all files accessible to shared user)

### Sharing System
- [ ] Create share link
- [ ] Access shared dataset
- [ ] Transfer ownership
- [ ] Share with chat enabled/disabled

### Web Connectors
- [ ] Create API connector
- [ ] Share API connector
- [ ] Access shared API data
- [ ] Chat with API connector data

### Agent System
- [ ] Agent created on shared dataset
- [ ] Shared user can chat with agent
- [ ] Agent accesses all files in multi-file dataset
- [ ] Agent respects permissions

---

## Notes

**Current Status** (Nov 4, 2025 - Updated):
- ✅ Agent-based architecture working
- ✅ Files uploaded to MindsDB
- ✅ Multi-file agents working
- ✅ File deletion from MindsDB working
- ✅ **Multi-file download IMPLEMENTED** (ZIP + individual file downloads)
- ✅ **Backend endpoints complete** (`/download-all` and `/files/{id}/download`)
- ✅ **Frontend UI complete** (Download buttons, file list, ZIP download)
- ⏳ Multi-file download needs live testing
- ⚠️  Sharing features need testing

**Implementation Completed**:
1. ✅ Multi-file download backend ([details](./MULTI_FILE_DOWNLOAD_IMPLEMENTATION.md))
2. ✅ Multi-file download frontend UI
3. ✅ FileUpload/DatasetFile compatibility layer
4. ✅ Comprehensive documentation

**Next Steps**:
1. ⏳ Test multi-file download with live backend
2. ⏳ Systematically test all sharing features
3. ⏳ Fix any issues found during testing
4. ⏳ Performance testing with large datasets
