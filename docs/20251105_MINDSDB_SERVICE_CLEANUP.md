# MindsDB Service Cleanup Plan

## Current State Analysis

The MindsDB service file has **2,851 lines** with **40 methods**, many of which are legacy code from the pre-agent era.

## Methods Status

### ✅ Keep - Agent-Based (Core Functionality)
These are essential for the agent-based architecture:

1. **`__init__`** - Initialize service
2. **`_ensure_connection`** - Connection management
3. **`health_check`** - Service health monitoring
4. **`execute_query`** - Raw SQL execution
5. **`create_or_get_agent`** - Core agent creation (CRITICAL)
6. **`update_agent`** - Update agent configuration
7. **`delete_agent`** - Clean up agents
8. **`list_agents`** - Debug/monitoring
9. **`setup_single_file_agent`** - Single file dataset agent setup (CRITICAL)
10. **`setup_multi_file_agent`** - Multi-file dataset agent setup (CRITICAL)
11. **`chat_with_dataset_agent`** - Main chat interface (CRITICAL)
12. **`_build_single_file_prompt`** - Prompt engineering for single file
13. **`_build_multi_file_prompt`** - Prompt engineering for multi-file

### ✅ Keep - File/Database Management (Supporting)
These support agent operations:

14. **`create_dataset_connection`** - Create dataset connectors
15. **`query_dataset`** - Query datasets
16. **`create_file_database_connector`** - File-based connectors
17. **`test_file_database_connector`** - Test connectors
18. **`delete_database_connector`** - Clean up connectors
19. **`upload_file_to_mindsdb`** - File uploads
20. **`delete_file_from_mindsdb`** - File cleanup
21. **`is_supported_file_type`** - File validation
22. **`get_file_type`** - File type detection

### ⚠️ Keep - Backward Compatibility (Minimal)
Keep only the wrapper:

23. **`chat_with_dataset`** - Wrapper to `chat_with_dataset_agent` (keep for API compatibility)

### ❌ Remove - Legacy Gemini Direct (Deprecated)
These are from the old direct Gemini approach:

24. **`create_gemini_engine`** - ~~Creates Gemini engine~~ (Agents don't need this)
25. **`create_gemini_model`** - ~~Creates Gemini models~~ (Agents don't need this)
26. **`ai_chat`** - ~~Direct chat with Gemini~~ (Replaced by agents)
27. **`_fallback_gemini_chat`** - ~~Gemini fallback~~ (Agent-based is mandatory)

### ❌ Remove - Unused/Redundant (Dead Code)
These appear unused or redundant:

28. **`create_web_connector`** - If not used by agents
29. **`test_web_connector`** - If not used
30. **`create_dataset_from_web_connector`** - If not used
31. **`_check_if_file_needs_mindsdb_setup`** - Internal helper, may be redundant
32. **`_setup_file_processing_automatically`** - May be redundant with agent setup
33. **`_upload_file_to_mindsdb_internal`** - Duplicate of `upload_file_to_mindsdb`?
34. **`_create_model_for_file_internal`** - Model creation (agents don't use models)
35. **`create_dataset_ml_model`** - ~~Old model-based approach~~
36. **`delete_dataset_models`** - ~~Old model cleanup~~
37. **`create_model_for_uploaded_file`** - ~~Model creation~~
38. **`setup_file_dataset_processing`** - May be redundant with agent setup
39. **`get_model_config`** - ~~Model configuration~~ (agents use different config)

## Dependencies Check

Before removing methods, verify they're not called:

```bash
# Check each method is unused
grep -r "method_name" backend/app --include="*.py" | grep -v "mindsdb.py:"
```

### Known Dependencies
- `create_gemini_model` - Used in `connector_service.py` (NEEDS REFACTORING)
- `ai_chat` - May be referenced in old code
- `chat_with_dataset` - Used as wrapper (KEEP)

## Cleanup Strategy

### Phase 1: Mark as Deprecated (Safe)
1. Add `@deprecated` decorator to old methods
2. Add logging warnings when called
3. Keep functionality for now

### Phase 2: Remove Direct Gemini (After testing)
1. Remove `create_gemini_engine`
2. Remove `create_gemini_model` (after refactoring connector_service.py)
3. Remove `ai_chat`
4. Remove `_fallback_gemini_chat`

### Phase 3: Remove Model-Based Code
1. Remove all model creation/management methods
2. Keep only agent-based methods

### Phase 4: Clean Up Helpers
1. Review and remove internal helpers
2. Consolidate duplicate functionality

## Expected Result

**Target**: Reduce from 2,851 lines / 40 methods to ~1,200 lines / 20 methods

### Core Methods (After Cleanup)
```python
class MindsDBService:
    # Connection Management
    - __init__
    - _ensure_connection
    - health_check
    - execute_query

    # Agent Management (CORE)
    - create_or_get_agent
    - update_agent
    - delete_agent
    - list_agents
    - setup_single_file_agent
    - setup_multi_file_agent
    - chat_with_dataset_agent
    - _build_single_file_prompt
    - _build_multi_file_prompt

    # File/Database Management
    - create_dataset_connection
    - create_file_database_connector
    - delete_database_connector
    - upload_file_to_mindsdb
    - delete_file_from_mindsdb
    - is_supported_file_type
    - get_file_type

    # Backward Compatibility
    - chat_with_dataset (wrapper only)
```

## Refactoring Needed

### connector_service.py
Currently calls `create_gemini_model` - needs to use agents instead:

```python
# OLD
result = self.mindsdb_service.create_gemini_model(...)

# NEW
result = self.mindsdb_service.setup_single_file_agent(dataset, db)
```

### Testing Plan
1. Test agent creation for single-file datasets
2. Test agent creation for multi-file datasets
3. Test chat functionality
4. Test file uploads
5. Test connectors
6. Verify no calls to removed methods

## Implementation Plan

1. **Create backup** of mindsdb.py
2. **Add deprecation warnings** to old methods
3. **Refactor connector_service.py** to use agents
4. **Remove deprecated methods** one by one
5. **Test thoroughly** after each removal
6. **Update documentation**

## Benefits

- **Cleaner codebase**: 60% reduction in code
- **Easier maintenance**: Only agent-based code
- **Better performance**: No legacy overhead
- **Clear architecture**: Agent-only approach
- **Reduced confusion**: No mixed methodologies

---

**Next Step**: Implement Phase 1 (Mark as Deprecated)
