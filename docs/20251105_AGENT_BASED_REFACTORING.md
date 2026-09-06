# Entrust Data Sharing MCP Platform - Agent-Based Refactoring

## Overview

This document describes the complete refactoring of the platform from a direct Gemini API-based system to a MindsDB agent-based architecture.

## Product Name Change

**Previous**: AI Share Platform
**Current**: Entrust Data Sharing MCP Platform

## Architecture Changes

### Previous Methodology
- Direct Gemini API calls for chat functionality
- Mixed approach with both MindsDB and direct LLM usage
- Chat with dataset using direct API

### Current Methodology
- **MindsDB agents exclusively** for all AI interactions
- Agent-based architecture for dataset interactions
- No direct LLM API calls from the application
- All AI functionality routed through MindsDB agent framework

## File Type Support Changes

### Previous Supported Types
```
csv, json, xlsx, xls, txt, pdf, docx, doc, rtf, odt, jpg, jpeg, png, gif, bmp, webp
```

### Current Supported Types (MindsDB Agent-Optimized)
```
CSV, XLSX, XLS, JSON, TXT, PDF, Parquet
```

### Rationale
- **Focus on structured data**: MindsDB agents work best with tabular/structured data
- **Removed image support**: Not supported by MindsDB agent architecture
- **Removed legacy document formats**: DOCX, DOC, RTF, ODT not supported
- **Added Parquet**: Modern columnar format for big data
- **Retained PDF and TXT**: For document-based datasets

## Configuration Changes

### Backend Changes

#### [backend/app/core/config.py](../backend/app/core/config.py)
```python
# Changed
PROJECT_NAME: str = "Entrust Data Sharing MCP Platform"
VERSION: str = "2.0.0"

# File types updated
ALLOWED_FILE_TYPES: str = "csv,xlsx,xls,json,txt,pdf,parquet"

# AI Configuration
DEFAULT_LLM_PROVIDER: str = "mindsdb"
MINDSDB_AGENT_MODEL: str = "gpt-4"

# Agent-based is now mandatory
USE_AGENT_BASED_CHAT: bool = True (mandatory)
AGENT_CHAT_ENABLE_FALLBACK: bool = False (no fallback)
```

#### [backend/.env.example](../backend/.env.example)
```bash
# Updated file types
ALLOWED_FILE_TYPES=csv,xlsx,xls,json,txt,pdf,parquet

# Agent-based configuration
DEFAULT_LLM_PROVIDER=mindsdb
MINDSDB_AGENT_MODEL=gpt-4
USE_AGENT_BASED_CHAT=true
AGENT_CHAT_ENABLE_FALLBACK=false

# Image processing disabled
ENABLE_IMAGE_PROCESSING=false
SUPPORTED_IMAGE_TYPES=

# Document types limited
SUPPORTED_DOCUMENT_TYPES=pdf,txt
```

### Frontend Changes

#### [frontend/src/app/layout.tsx](../frontend/src/app/layout.tsx)
```typescript
export const metadata: Metadata = {
  title: "Entrust Data Sharing MCP Platform",
  description: "Enterprise data sharing platform powered by MindsDB agents..."
};
```

#### [frontend/src/app/page.tsx](../frontend/src/app/page.tsx)
- Updated hero section with new branding
- Changed "AI Share Platform" to "Entrust Data Sharing MCP Platform"
- Updated tagline to reflect agent-based architecture

### MindsDB Service Refactoring

#### [backend/app/services/mindsdb.py](../backend/app/services/mindsdb.py)

**Key Changes:**
1. Added comprehensive documentation header explaining agent-based architecture
2. Updated initialization to focus on agent configuration
3. Deprecated direct Gemini configuration (kept for backward compatibility)
4. Added agent model configuration (`MINDSDB_AGENT_MODEL`)
5. Updated logging to reflect agent-based methodology

**Deprecated Features (kept for backward compatibility):**
- Direct Gemini API configuration
- Legacy model configurations
- Direct LLM fallback mechanisms

## Migration Guide

### For Developers

1. **Update Environment Variables**:
   ```bash
   # Update your .env file
   USE_AGENT_BASED_CHAT=true
   AGENT_CHAT_ENABLE_FALLBACK=false
   DEFAULT_LLM_PROVIDER=mindsdb
   ALLOWED_FILE_TYPES=csv,xlsx,xls,json,txt,pdf,parquet
   ```

2. **File Upload Validation**:
   - Update any file upload logic to validate against new supported types
   - Remove references to unsupported formats (images, DOCX, etc.)

3. **Chat Functionality**:
   - All chat interactions now go through MindsDB agents
   - No need to manage direct LLM API calls
   - Agent handles context, memory, and multi-file datasets

### For Users

1. **File Uploads**:
   - Only upload supported file types: CSV, XLSX, XLS, JSON, TXT, PDF, Parquet
   - Image files are no longer supported
   - Convert DOCX/DOC to PDF or TXT before uploading

2. **Chat Functionality**:
   - Chat experience remains the same
   - Backend now uses more robust agent-based approach
   - Better support for multi-file datasets
   - More consistent responses

### For Administrators

1. **MindsDB Setup**:
   - Ensure MindsDB server is running and accessible
   - Configure agents through MindsDB interface
   - Set up LLM provider credentials in MindsDB (not directly in app)

2. **Database Migration**:
   - No database schema changes required
   - Existing datasets remain compatible
   - Consider migrating unsupported file types

## Benefits of Agent-Based Architecture

### Performance
- **Better context handling**: Agents maintain conversation context
- **Optimized queries**: Agents generate more efficient data queries
- **Reduced latency**: Direct MindsDB connection eliminates API roundtrips

### Scalability
- **Centralized AI management**: All AI through MindsDB
- **Easy model switching**: Change models without code changes
- **Multi-user support**: Better handling of concurrent requests

### Functionality
- **Multi-file datasets**: Agents can work across multiple files
- **Advanced analytics**: Built-in data analysis capabilities
- **Consistent responses**: More reliable AI behavior

### Maintainability
- **Single AI interface**: Only MindsDB agents to maintain
- **No API key juggling**: Credentials managed in MindsDB
- **Cleaner codebase**: Removed direct LLM API code

## Testing Checklist

- [ ] File upload with CSV file
- [ ] File upload with XLSX file
- [ ] File upload with JSON file
- [ ] File upload with PDF file
- [ ] File upload with Parquet file
- [ ] File upload with unsupported type (should fail gracefully)
- [ ] Chat with single-file dataset
- [ ] Chat with multi-file dataset
- [ ] Share dataset functionality
- [ ] Download dataset functionality
- [ ] Connector-based datasets

## Backward Compatibility

### What's Preserved
- Database schema unchanged
- API endpoints unchanged
- Existing datasets remain functional
- User authentication unchanged
- Sharing functionality unchanged

### What's Deprecated
- Direct Gemini API calls (code kept but not used)
- Image file support
- DOCX, DOC, RTF, ODT file support
- Fallback to direct LLM (agent-based is mandatory)

## Documentation Updates

- [x] README.md - Updated with new branding and architecture
- [x] .env.example - Updated with new configuration
- [x] config.py - Updated with new defaults
- [x] MindsDB service - Added comprehensive documentation

## Rollback Plan

If issues arise, you can temporarily enable fallback by:

```bash
# In .env
AGENT_CHAT_ENABLE_FALLBACK=true
```

However, this is **not recommended** as the platform is designed for agent-based architecture.

## Support

For questions or issues:
1. Check MindsDB agent configuration
2. Verify supported file types
3. Review MindsDB logs for agent errors
4. Ensure MindsDB server is accessible

## Version History

- **v2.0.0** (Current) - Full agent-based architecture, renamed to Entrust MCP Platform
- **v1.0.0** (Previous) - Mixed approach with direct Gemini API

---

**Entrust Data Sharing MCP Platform** - Powered by MindsDB Agents
