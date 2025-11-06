# File Update and Management Guide

**Date**: November 4, 2025

## Overview

This document explains how the system handles file updates, deletions, and what happens when dataset files change.

## File Storage Architecture

### Storage Layers

1. **S3/MinIO Storage** - Primary file storage
   - All uploaded files stored in S3-compatible storage
   - Organized by organization: `org_{org_id}/dataset_{id}_...`
   - Files persist until explicitly deleted

2. **Database Records** - File metadata
   - `FileUpload` table: MindsDB agent files
   - `DatasetFile` table: Multi-file dataset tracking
   - Contains: filename, path, size, type, upload status

3. **MindsDB Files** - For agent access
   - Files uploaded to MindsDB via API: `PUT /api/files/{filename}`
   - Referenced in agents as: `files.dataset_{id}_file_{file_id}`
   - Agents can query these files directly

## File Lifecycle

### 1. File Upload

```mermaid
Upload → S3 Storage → Database Record → MindsDB Upload → Agent Creation/Update
```

**Process**:
1. User uploads file(s) via API or UI
2. Files saved to S3/MinIO with unique paths
3. `FileUpload` record created in database
4. File downloaded from S3 and uploaded to MindsDB
5. Agent created/updated with file references

**Code**: [backend/app/services/mindsdb.py:1154-1204](../backend/app/services/mindsdb.py#L1154-L1204)

### 2. File Update/Replacement

**Current Status**: ⚠️ NOT FULLY IMPLEMENTED

**What SHOULD happen when a file is updated**:

1. **Upload new file version**
   ```python
   # New file uploaded to S3 with new path
   new_file_path = f"org_{org_id}/dataset_{id}_v2_{timestamp}.csv"
   ```

2. **Update database record**
   ```python
   file_upload.file_path = new_file_path
   file_upload.file_size = new_size
   file_upload.updated_at = datetime.utcnow()
   ```

3. **Update MindsDB file**
   ```python
   # Delete old file from MindsDB
   mindsdb_service.delete_file_from_mindsdb(old_filename)

   # Upload new version
   mindsdb_service.upload_file_to_mindsdb(new_file_path, filename)
   ```

4. **Update or recreate agent**
   ```python
   # Option A: Agent automatically uses updated file (MindsDB handles this)
   # Option B: Recreate agent with new file references
   mindsdb_service.create_or_update_multi_file_agent(dataset_id, force_recreate=True)
   ```

**Recommended Implementation**:

```python
@router.put("/{dataset_id}/files/{file_id}")
async def update_file(
    dataset_id: int,
    file_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a specific file in a dataset.

    Steps:
    1. Verify ownership
    2. Upload new file to S3
    3. Delete old file from S3
    4. Update database record
    5. Update MindsDB file
    6. Update agent if necessary
    """
    # Get existing file record
    file_record = db.query(FileUpload).filter(
        FileUpload.id == file_id,
        FileUpload.dataset_id == dataset_id
    ).first()

    if not file_record:
        raise HTTPException(404, "File not found")

    # Check ownership
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if dataset.owner_id != current_user.id:
        raise HTTPException(403, "Not authorized")

    # Upload new version to S3
    file_content = await file.read()
    new_storage_result = await storage_service.store_dataset_file(
        file_content=file_content,
        original_filename=file.filename,
        dataset_id=dataset_id,
        organization_id=dataset.organization_id
    )

    # Delete old version from S3
    await storage_service.delete_dataset_file(file_record.file_path)

    # Update MindsDB file
    mindsdb_file_name = f"dataset_{dataset_id}_file_{file_id}"

    # Delete old from MindsDB
    mindsdb_service.delete_file_from_mindsdb(mindsdb_file_name)

    # Upload new to MindsDB
    import boto3, tempfile, os
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'),
        endpoint_url=os.getenv('S3_ENDPOINT_URL')
    )

    temp_file = tempfile.NamedTemporaryFile(delete=False)
    s3_client.download_file(
        os.getenv('S3_BUCKET_NAME'),
        new_storage_result['file_path'],
        temp_file.name
    )

    mindsdb_service.upload_file_to_mindsdb(temp_file.name, mindsdb_file_name)
    os.remove(temp_file.name)

    # Update database record
    file_record.file_path = new_storage_result['file_path']
    file_record.file_size = len(file_content)
    file_record.updated_at = datetime.utcnow()

    # Update dataset timestamp
    dataset.updated_at = datetime.utcnow()

    db.commit()

    # Agent will automatically use updated file
    # MindsDB agents reference files by name, so updating the file content
    # doesn't require recreating the agent

    return {
        "message": "File updated successfully",
        "file_id": file_id,
        "filename": file.filename,
        "size": len(file_content),
        "updated_at": file_record.updated_at.isoformat()
    }
```

### 3. File Deletion

**Current Status**: ✅ IMPLEMENTED

When a dataset is deleted:

1. **Delete from MindsDB**
   ```python
   # Delete files from MindsDB files database
   for file_upload in file_uploads:
       mindsdb_file_name = f"dataset_{file_upload.dataset_id}_file_{file_upload.id}"
       mindsdb_service.delete_file_from_mindsdb(mindsdb_file_name)
   ```

2. **Delete from S3**
   ```python
   # Delete from S3/MinIO storage
   await storage_service.delete_dataset_file(file_upload.file_path)
   ```

3. **Delete database records**
   ```python
   # Soft delete or hard delete depending on force_delete flag
   db.query(FileUpload).filter(FileUpload.dataset_id == dataset_id).delete()
   ```

**Code**: [backend/app/api/datasets.py:647-676](../backend/app/api/datasets.py#L647-L676)

## Agent Behavior with File Updates

### How MindsDB Agents Handle File Changes

**Important**: MindsDB agents reference files by **name**, not by content hash. This means:

✅ **Updating file content**: Agent automatically sees new data (after MindsDB file is updated)
❌ **Renaming files**: Requires agent recreation with new file references
❌ **Adding/removing files**: Requires agent recreation

### Agent Update Scenarios

#### Scenario 1: File Content Changed (Same Name)
```python
# Update file in MindsDB
mindsdb_service.delete_file_from_mindsdb("dataset_10_file_5")
mindsdb_service.upload_file_to_mindsdb(new_content, "dataset_10_file_5")

# Agent automatically uses new content
# No agent recreation needed
```

#### Scenario 2: File Added to Dataset
```python
# Upload new file to MindsDB
mindsdb_service.upload_file_to_mindsdb(new_file, "dataset_10_file_6")

# Recreate agent with updated table list
tables = [
    "files.dataset_10_file_5",
    "files.dataset_10_file_6"  # New file
]
mindsdb_service.create_or_update_multi_file_agent(
    dataset_id=10,
    tables=tables,
    force_recreate=True
)
```

#### Scenario 3: File Removed from Dataset
```python
# Delete file from MindsDB
mindsdb_service.delete_file_from_mindsdb("dataset_10_file_5")

# Recreate agent without the removed file
tables = [
    "files.dataset_10_file_6"  # Only remaining file
]
mindsdb_service.create_or_update_multi_file_agent(
    dataset_id=10,
    tables=tables,
    force_recreate=True
)
```

## Best Practices

### File Version Management

**Recommendation**: Keep file history for rollback capability

```python
class FileVersion(Base):
    """Track file versions for rollback"""
    __tablename__ = "file_versions"

    id = Column(Integer, primary_key=True)
    file_upload_id = Column(Integer, ForeignKey("file_uploads.id"))
    version_number = Column(Integer)
    file_path = Column(String)  # S3 path for this version
    file_size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
```

### File Update Notifications

**Recommendation**: Notify users when shared dataset files are updated

```python
async def notify_file_update(dataset_id: int, file_id: int):
    """Notify all users with access to dataset"""
    # Get all users with share access
    share_accesses = db.query(DatasetShareAccess).filter(
        DatasetShareAccess.dataset_id == dataset_id
    ).all()

    for access in share_accesses:
        # Send email/notification
        await send_notification(
            user_id=access.user_id,
            message=f"File updated in shared dataset: {dataset.name}"
        )
```

### Agent Cache Invalidation

**Recommendation**: Clear any caching when files update

```python
def invalidate_agent_cache(dataset_id: int):
    """Invalidate caching layers when dataset files change"""
    # Clear preview cache
    cache.delete(f"preview:{dataset_id}")

    # Clear metadata cache
    cache.delete(f"metadata:{dataset_id}")

    # Update dataset timestamp
    dataset.updated_at = datetime.utcnow()
```

## Testing File Updates

### Test Case 1: Update Single File Content

```bash
# 1. Upload initial dataset
curl -X POST http://localhost:8000/api/datasets/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@data_v1.csv"

# 2. Chat with agent - note the data
curl -X POST http://localhost:8000/api/datasets/$ID/chat \
  -d '{"message":"How many rows?"}' # Returns: 100 rows

# 3. Update file with new version (more rows)
curl -X PUT http://localhost:8000/api/datasets/$ID/files/$FILE_ID \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data_v2.csv"  # 200 rows

# 4. Chat again - should see updated data
curl -X POST http://localhost:8000/api/datasets/$ID/chat \
  -d '{"message":"How many rows?"}' # Should return: 200 rows
```

### Test Case 2: Add File to Multi-File Dataset

```bash
# 1. Create dataset with 1 file
curl -X POST http://localhost:8000/api/datasets/upload \
  -F "files=@customers.csv"

# 2. Add second file
curl -X POST http://localhost:8000/api/datasets/$ID/files \
  -F "file=@orders.csv"

# 3. Agent should be recreated with both files
curl -X POST http://localhost:8000/api/datasets/$ID/chat \
  -d '{"message":"What tables are available?"}'
# Should list both customers and orders
```

### Test Case 3: Remove File from Dataset

```bash
# 1. Create multi-file dataset
curl -X POST http://localhost:8000/api/datasets/upload \
  -F "files=@file1.csv" \
  -F "files=@file2.csv"

# 2. Delete one file
curl -X DELETE http://localhost:8000/api/datasets/$ID/files/$FILE_ID

# 3. Agent should work with remaining file only
curl -X POST http://localhost:8000/api/datasets/$ID/chat \
  -d '{"message":"List tables"}'
# Should show only file1
```

## Monitoring File Changes

### Audit Log

Every file operation should be logged:

```python
class FileAuditLog(Base):
    """Track all file operations"""
    __tablename__ = "file_audit_log"

    id = Column(Integer, primary_key=True)
    file_upload_id = Column(Integer)
    dataset_id = Column(Integer)
    action = Column(String)  # 'upload', 'update', 'delete'
    user_id = Column(Integer)
    ip_address = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON)  # Additional context
```

### Metrics to Track

1. **File Update Frequency**: How often files are updated
2. **Agent Recreation Count**: How many times agents are recreated
3. **Download Impact**: Downloads after file updates
4. **Chat Quality**: Agent response quality after updates

## Troubleshooting

### Issue: Agent Returns Old Data After File Update

**Cause**: File wasn't properly updated in MindsDB

**Solution**:
```python
# Force refresh
mindsdb_file_name = f"dataset_{dataset_id}_file_{file_id}"

# Delete and re-upload
mindsdb_service.delete_file_from_mindsdb(mindsdb_file_name)
mindsdb_service.upload_file_to_mindsdb(file_path, mindsdb_file_name)

# Verify in MindsDB
# SHOW TABLES FROM files; -- Should show the file
# SELECT * FROM files.dataset_X_file_Y LIMIT 5; -- Should show new data
```

### Issue: Download Returns Old File Version

**Cause**: File reference not updated in database

**Solution**:
```python
# Check file_path in database
file_record = db.query(FileUpload).filter(FileUpload.id == file_id).first()
print(f"Current path: {file_record.file_path}")

# Should point to new S3 path, not old one
```

### Issue: Multi-File Agent Missing Updated File

**Cause**: Agent not recreated after file addition/removal

**Solution**:
```python
# Force agent recreation
mindsdb_service.create_or_update_multi_file_agent(
    dataset_id=dataset_id,
    force_recreate=True
)
```

## Future Enhancements

1. **Automatic File Versioning**: Store all versions automatically
2. **Diff Views**: Show what changed between versions
3. **Rollback UI**: Easy rollback to previous versions
4. **Change Notifications**: Real-time updates via WebSocket
5. **Conflict Resolution**: Handle concurrent file updates
6. **Incremental Updates**: For large files, only upload changes

## Summary

### Current Implementation Status

- ✅ **File Upload**: Working with S3 and MindsDB integration
- ✅ **File Deletion**: Complete cleanup across all systems
- ✅ **Agent Access**: Agents can query files correctly
- ⚠️  **File Update**: Not yet implemented (recommended above)
- ⚠️  **Version History**: Not implemented
- ⚠️  **Change Notifications**: Not implemented

### Key Takeaways

1. Files are stored in **three places**: S3, Database, MindsDB
2. All three must be kept **in sync** for proper operation
3. Agent updates depend on whether **files change or table structure changes**
4. **File updates require careful coordination** across all systems
5. **Audit logging** is essential for debugging file issues

---

**Next Steps**: Implement file update endpoint and test thoroughly with agents.
