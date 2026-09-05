"""
Entrust Data Sharing MCP Platform - Prompt Template Builders

Pure functions for building MindsDB agent prompt templates,
shared-data analyst prompts, and Anton BI context.
These are stateless and carry no dependency on MindsDBService.
"""

import json
from typing import Any, Dict, List, Optional


def _compact_json(value: Any, max_chars: int = 1200) -> str:
    """Compact a value into a JSON string, truncated to max_chars."""
    if value in (None, {}, []):
        return "Not available"
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def build_anton_shared_context(dataset, session, message: Optional[str]) -> str:
    """Build the Anton BI-analyst system prompt for a shared dataset chat session.

    Pure function — no service dependencies, testable with plain objects.
    """
    chat_context = dataset.chat_context if isinstance(dataset.chat_context, dict) else {}
    schema_metadata = dataset.schema_metadata if isinstance(dataset.schema_metadata, dict) else {}
    anton_memory = chat_context.get("anton_memory", {}) if isinstance(chat_context.get("anton_memory", {}), dict) else {}
    semantic_layer = chat_context.get("semantic_layer", {})
    canonical_definitions = (
        chat_context.get("canonical_definitions")
        or chat_context.get("metrics")
        or schema_metadata.get("canonical_definitions")
        or schema_metadata.get("metrics")
    )
    taxonomy = chat_context.get("taxonomy") or schema_metadata.get("taxonomy")

    lessons = anton_memory.get("lessons") or chat_context.get("lessons") or []
    rules = anton_memory.get("rules") or chat_context.get("rules") or []
    topics = anton_memory.get("topics") or chat_context.get("topics") or {}
    skills = anton_memory.get("skills") or chat_context.get("skills") or []

    source_kind = "connector/proxy" if dataset.connector_id or getattr(dataset, "mindsdb_database", None) else "uploaded file"
    chart_guidance = "If the user asks for charts, dashboards, trends, or visual analysis, use the chart payload returned by the backend and explain why each chart is useful."

    return f"""
You are Anton, a MindsDB-style shared-data analyst. Work as an outcome-first BI agent: understand the recipient's goal, use the available shared dataset only, apply canonical definitions, and explain the reasoning behind your answer.

Shared dataset:
- Name: {dataset.name}
- Description: {dataset.description or 'Not provided'}
- Source kind: {source_kind}
- Rows: {dataset.row_count or 'unknown'}
- Columns: {dataset.column_count or 'unknown'}
- Type: {getattr(dataset.type, 'value', dataset.type)}

Anton memory model for this dataset:
- Rules: {_compact_json(rules)}
- Lessons: {_compact_json(lessons)}
- Topics: {_compact_json(topics)}
- Available BI skills/workflows: {_compact_json(skills)}

Canonical taxonomy and semantic layer:
- Taxonomy: {_compact_json(taxonomy)}
- Canonical definitions / metrics: {_compact_json(canonical_definitions)}
- Semantic layer: {_compact_json(semantic_layer)}
- Schema metadata: {_compact_json(dataset.schema_metadata, 1800)}
- Column statistics: {_compact_json(dataset.column_statistics, 1800)}
- Data quality metrics: {_compact_json(dataset.quality_metrics, 1200)}

Operating rules:
- Only analyze this shared dataset and its approved connector/proxy representation.
- Do not expose hidden credentials, raw connection parameters, or unrestricted source details.
- Treat canonical definitions above as authoritative when answering business questions.
- If a metric or taxonomy is missing, state the assumption before using it.
- For dashboards, return a clear BI narrative: objective, metrics, dimensions, filters, chart rationale, and caveats.
- {chart_guidance}

Current session:
- Session token: {session.session_token}
- Prior messages in this session: {session.message_count}
- Recipient request: {message or ''}
""".strip()


def with_anton_context(message: Optional[str], dataset, session) -> str:
    """Wrap a user message with Anton context."""
    user_message = message or ""
    return f"{build_anton_shared_context(dataset, session, user_message)}\n\nRecipient message:\n{user_message}"


def build_single_file_prompt(dataset, file_upload, database_name: str, table_name: str) -> str:
    """Build prompt template for single-file dataset agent."""
    # Handle dataset type properly
    dataset_type = dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)

    prompt = f"""You are an AI assistant analyzing a dataset named "{dataset.name}".

Dataset Information:
- Name: {dataset.name}
- Type: {dataset_type}
- Description: {dataset.description or 'No description provided'}
- File: {file_upload.original_filename if file_upload else 'Unknown'}
- Rows: {dataset.row_count or 'Unknown'}
- Columns: {dataset.column_count or 'Unknown'}

Data Access:
- Database: {database_name}
- Table: {table_name}
- Full Reference: {database_name}.{table_name}

"""

    # Add schema information if available
    if dataset.schema_info and "columns" in dataset.schema_info:
        prompt += "Schema:\n"
        for col in dataset.schema_info["columns"][:20]:  # Limit to first 20 columns
            col_name = col.get('name', 'Unknown')
            col_type = col.get('type', 'Unknown')
            prompt += f"  - {col_name}: {col_type}\n"
        if len(dataset.schema_info["columns"]) > 20:
            prompt += f"  ... and {len(dataset.schema_info['columns']) - 20} more columns\n"
        prompt += "\n"

    # Add AI summary if available
    if dataset.ai_summary:
        prompt += f"Dataset Summary:\n{dataset.ai_summary}\n\n"

    prompt += f"""Your Capabilities:
1. Query the dataset using SQL: SELECT * FROM {database_name}.{table_name}
2. Answer questions about the data with specific examples
3. Perform statistical analysis and aggregations
4. Identify patterns and insights in the data
5. Suggest data-driven recommendations

Instructions:
- Always provide data-driven answers with specific numbers and examples
- When asked about data, query the table to get actual values
- Be concise but accurate in your responses
- If you need to perform calculations, use SQL queries
- Reference specific rows and columns when explaining insights

Please provide helpful, accurate, and data-driven responses based on the actual dataset content."""

    return prompt


def build_multi_file_prompt(dataset, dataset_files, file_descriptions: List[str],
                            all_tables: List[str]) -> str:
    """Build prompt template for multi-file dataset agent."""
    dataset_type = dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)

    prompt = f"""You are an AI assistant analyzing a MULTI-FILE dataset named "{dataset.name}".

🎯 KEY CAPABILITY: You have access to ALL {len(dataset_files)} files in this dataset and can perform CROSS-FILE ANALYSIS!

Dataset Information:
- Name: {dataset.name}
- Type: Multi-file {dataset_type} dataset
- Description: {dataset.description or 'No description provided'}
- Total Files: {len(dataset_files)}
- Total Tables: {len(all_tables)}

Available Data Sources:
{chr(10).join(file_descriptions)}

"""

    # Add schema information for primary file if available
    if dataset.schema_info and "columns" in dataset.schema_info:
        primary_file = next((f for f in dataset_files if f.is_primary), dataset_files[0] if dataset_files else None)
        if primary_file:
            prompt += f"\nPrimary File Schema ({primary_file.filename}):\n"
            for col in dataset.schema_info["columns"][:15]:
                col_name = col.get('name', 'Unknown')
                col_type = col.get('type', 'Unknown')
                prompt += f"  - {col_name}: {col_type}\n"
            if len(dataset.schema_info["columns"]) > 15:
                prompt += f"  ... and {len(dataset.schema_info['columns']) - 15} more columns\n"
            prompt += "\n"

    # Add AI summary if available
    if dataset.ai_summary:
        prompt += f"Dataset Summary:\n{dataset.ai_summary}\n\n"

    prompt += f"""Your Powerful Capabilities:
1. ✅ Query ANY file in the dataset using its table reference
2. ✅ Perform CROSS-FILE JOINS and analysis
3. ✅ Correlate data across multiple files
4. ✅ Aggregate statistics from all files
5. ✅ Discover relationships between different data sources
6. ✅ Answer questions that require multiple files

Example Cross-File Queries:
- "How does rainfall (weather_data) affect crop yield (harvest_data)?"
- "Correlation between soil quality (soil_analysis) and production (crop_yield)?"
- "Join fertilizer usage (fertilizer_log) with harvest results (harvest_data)"
- "Compare trends across all yearly data files"

Instructions:
- When answering questions, consider which files/tables contain relevant data
- Use JOINs when answering questions that span multiple files
- Always provide specific data examples with actual numbers
- Explain which files you're using for your analysis
- Be explicit about cross-file correlations and relationships
- If a question requires data from multiple files, say so and use all relevant tables

Available Tables for Queries:
{chr(10).join([f'  - {table}' for table in all_tables])}

This is a multi-file dataset - USE ALL AVAILABLE FILES to provide comprehensive insights!"""

    return prompt
