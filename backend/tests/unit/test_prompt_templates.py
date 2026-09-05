"""
Unit tests for prompt_templates module — pure function prompt builders.

These are stateless functions with no external dependencies, so no mocking
is needed.  Simple mock objects (with the right attributes) are sufficient.
"""
import pytest
from unittest.mock import Mock, MagicMock

from app.services.prompt_templates import (
    _compact_json,
    build_anton_shared_context,
    with_anton_context,
    build_single_file_prompt,
    build_multi_file_prompt,
)


# ── _compact_json ────────────────────────────────────────────────────

class TestCompactJson:
    """_compact_json(value, max_chars)"""

    def test_none(self):
        """None returns 'Not available'."""
        assert _compact_json(None) == "Not available"

    def test_empty_dict(self):
        """Empty dict returns 'Not available'."""
        assert _compact_json({}) == "Not available"

    def test_empty_list(self):
        """Empty list returns 'Not available'."""
        assert _compact_json([]) == "Not available"

    def test_simple_dict(self):
        """A small dict is serialised as JSON."""
        result = _compact_json({"key": "value"})
        assert result == '{"key": "value"}'

    def test_list(self):
        """A list is serialised as JSON."""
        result = _compact_json([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_string(self):
        """A plain string is serialised (quoted JSON)."""
        result = _compact_json("hello")
        assert result == '"hello"'

    def test_truncation(self):
        """Values longer than max_chars are truncated with ellipsis."""
        long_value = {"data": "x" * 2000}
        result = _compact_json(long_value, max_chars=50)
        assert len(result) == 53  # 50 chars + "..."
        assert result.endswith("...")

    def test_no_truncation_when_fits(self):
        """Values shorter than max_chars are not truncated."""
        short = {"a": "short"}
        result = _compact_json(short, max_chars=100)
        assert not result.endswith("...")
        assert result == '{"a": "short"}'

    def test_truncation_boundary(self):
        """Value exactly at max_chars is not truncated."""
        value = "a" * 100
        result = _compact_json(value, max_chars=102)
        # JSON encoding adds quotes: '"aaa..."' — length becomes 102
        assert not result.endswith("...")

    def test_custom_max_chars(self):
        """max_chars parameter is respected."""
        value = {"k": "very long value"}
        result = _compact_json(value, max_chars=10)
        assert len(result) == 13  # 10 + "..."
        assert result.endswith("...")

    def test_type_error_fallback(self):
        """A value that cannot be JSON-serialised falls back to str()."""

        class Unserialisable:
            def __str__(self):
                return "fallback string"

        result = _compact_json(Unserialisable())
        # json.dumps with default=str produces a JSON string
        assert result == '"fallback string"'

    def test_type_error_truncation(self):
        """str() fallback is also truncated."""
        class LongUnserialisable:
            def __str__(self):
                return "x" * 500

        result = _compact_json(LongUnserialisable(), max_chars=10)
        assert len(result) == 13
        assert result.endswith("...")

    def test_int(self):
        """Integer values are serialised."""
        assert _compact_json(42) == "42"

    def test_bool(self):
        """Boolean values are serialised."""
        assert _compact_json(True) == "true"

    def test_nested_dict(self):
        """Nested structures are serialised."""
        data = {"outer": {"inner": [1, 2, 3]}}
        result = _compact_json(data)
        assert '"outer"' in result
        assert '"inner"' in result

    def test_ensure_ascii_false(self):
        """Non-ASCII characters are preserved."""
        result = _compact_json({"name": "cafe"})
        assert "cafe" in result


# ── build_anton_shared_context ───────────────────────────────────────

class TestBuildAntonSharedContext:
    """build_anton_shared_context(dataset, session, message)"""

    def test_basic_context(self):
        """Happy path: produces a prompt containing dataset name and session info."""
        dataset = Mock(
            name="Sales Data",
            description="Monthly sales figures",
            connector_id=None,
            mindsdb_database=None,
            row_count=5000,
            column_count=12,
            type=Mock(value="csv"),
            chat_context={
                "anton_memory": {"lessons": [], "rules": [], "topics": {}, "skills": []},
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_abc123", message_count=3)

        prompt = build_anton_shared_context(dataset, session, "Show me revenue by region")

        assert "Sales Data" in prompt
        assert "sess_abc123" in prompt
        assert "3" in prompt
        assert "Show me revenue by region" in prompt
        assert "uploaded file" in prompt  # source_kind for non-connector datasets
        assert "Anton" in prompt
        assert "Not available" in prompt  # empty lists become "Not available"

    def test_connector_source_kind(self):
        """Connector-based datasets show 'connector/proxy' source kind."""
        dataset = Mock(
            name="DB Dataset",
            description=None,
            connector_id=5,
            mindsdb_database=None,
            row_count=None,
            column_count=None,
            type=Mock(value="database"),
            chat_context={},
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_xyz", message_count=0)

        prompt = build_anton_shared_context(dataset, session, None)

        assert "connector/proxy" in prompt
        assert "Not provided" in prompt  # description is None

    def test_mindsdb_database_source_kind(self):
        """Dataset with mindsdb_database also shows 'connector/proxy'."""
        dataset = Mock(
            name="MindsDB Dataset",
            description="From MindsDB",
            connector_id=None,
            mindsdb_database="my_mindsdb",
            row_count=100,
            column_count=5,
            type=Mock(value="csv"),
            chat_context={},
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_mdb", message_count=1)

        prompt = build_anton_shared_context(dataset, session, "Analyze trends")

        assert "connector/proxy" in prompt

    def test_chat_context_is_none(self):
        """When chat_context is None, defaults to empty dict."""
        dataset = Mock(
            name="No Context",
            description="Dataset without chat context",
            connector_id=None,
            mindsdb_database=None,
            row_count=10,
            column_count=3,
            type=Mock(value="csv"),
            chat_context=None,
            schema_metadata=None,
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_none", message_count=0)

        prompt = build_anton_shared_context(dataset, session, None)

        assert "No Context" in prompt
        assert "Not available" in prompt  # empty defaults

    def test_anton_memory_fields(self):
        """Anton memory fields (rules, lessons, topics, skills) appear in prompt."""
        dataset = Mock(
            name="Memory Dataset",
            description="Has memories",
            connector_id=None,
            mindsdb_database=None,
            row_count=100,
            column_count=5,
            type=Mock(value="csv"),
            chat_context={
                "anton_memory": {
                    "lessons": ["Always check for nulls"],
                    "rules": ["Use ISO dates"],
                    "topics": {"finance": ["revenue", "costs"]},
                    "skills": ["SQL", "Python"],
                },
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_mem", message_count=5)

        prompt = build_anton_shared_context(dataset, session, "Tell me about data")

        assert "Always check for nulls" in prompt
        assert "Use ISO dates" in prompt
        assert "finance" in prompt
        assert "SQL" in prompt

    def test_canonical_definitions_from_chat_context(self):
        """Canonical definitions are sourced from chat_context first."""
        dataset = Mock(
            name="Canonical Dataset",
            description="With definitions",
            connector_id=None,
            mindsdb_database=None,
            row_count=50,
            column_count=4,
            type=Mock(value="csv"),
            chat_context={
                "canonical_definitions": {"revenue": "sum of sales"},
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_canon", message_count=2)

        prompt = build_anton_shared_context(dataset, session, "What is revenue?")

        assert "revenue" in prompt
        assert "sum of sales" in prompt

    def test_canonical_definitions_fallback_to_metrics(self):
        """Canonical definitions fall back to chat_context.metrics."""
        dataset = Mock(
            name="Metrics Dataset",
            description="Fallback test",
            connector_id=None,
            mindsdb_database=None,
            row_count=100,
            column_count=3,
            type=Mock(value="csv"),
            chat_context={
                "metrics": {"profit": "revenue - costs"},
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_metrics", message_count=1)

        prompt = build_anton_shared_context(dataset, session, "Profit?")

        assert "profit" in prompt
        assert "revenue - costs" in prompt

    def test_canonical_definitions_fallback_to_schema_metadata(self):
        """Canonical definitions fall back to schema_metadata.canonical_definitions."""
        dataset = Mock(
            name="Schema Metadata",
            description="Deep fallback",
            connector_id=None,
            mindsdb_database=None,
            row_count=100,
            column_count=3,
            type=Mock(value="csv"),
            chat_context={},
            schema_metadata={
                "canonical_definitions": {"metric_a": "definition_a"},
            },
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_schema", message_count=1)

        prompt = build_anton_shared_context(dataset, session, "Explain metric_a")

        assert "metric_a" in prompt
        assert "definition_a" in prompt

    def test_taxonomy_from_chat_context(self):
        """Taxonomy is sourced from chat_context.taxonomy."""
        dataset = Mock(
            name="Taxonomy Dataset",
            description=None,
            connector_id=None,
            mindsdb_database=None,
            row_count=200,
            column_count=6,
            type=Mock(value="csv"),
            chat_context={
                "taxonomy": {"category": ["A", "B", "C"]},
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_tax", message_count=3)

        prompt = build_anton_shared_context(dataset, session, "Categories?")

        assert "category" in prompt

    def test_lessons_fallback_to_chat_context_lessons(self):
        """lessons fall back from anton_memory to chat_context top-level."""
        dataset = Mock(
            name="Lessons Fallback",
            description=None,
            connector_id=None,
            mindsdb_database=None,
            row_count=10,
            column_count=2,
            type=Mock(value="csv"),
            chat_context={
                "lessons": ["Fallback lesson"],
                "semantic_layer": {},
            },
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_lfb", message_count=0)

        prompt = build_anton_shared_context(dataset, session, None)

        assert "Fallback lesson" in prompt

    def test_empty_message(self):
        """Empty message results in empty recipient request string."""
        dataset = Mock(
            name="Empty Msg",
            description="Test",
            connector_id=None,
            mindsdb_database=None,
            row_count=1,
            column_count=1,
            type=Mock(value="csv"),
            chat_context={},
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="sess_empty", message_count=0)

        prompt = build_anton_shared_context(dataset, session, "")

        # The message placeholder should be empty
        assert "Recipient request:" in prompt


# ── with_anton_context ───────────────────────────────────────────────

class TestWithAntonContext:
    """with_anton_context(message, dataset, session)"""

    def test_wraps_message(self):
        """Result contains the context and the message."""
        dataset = Mock(
            name="Test",
            description="desc",
            connector_id=None,
            mindsdb_database=None,
            row_count=1,
            column_count=1,
            type=Mock(value="csv"),
            chat_context={},
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="s", message_count=0)

        result = with_anton_context("Hello", dataset, session)

        assert "Anton" in result  # from context
        assert "Hello" in result  # the message
        assert "Recipient message:" in result

    def test_none_message(self):
        """None message is treated as empty string."""
        dataset = Mock(
            name="None Msg",
            description="desc",
            connector_id=None,
            mindsdb_database=None,
            row_count=1,
            column_count=1,
            type=Mock(value="csv"),
            chat_context={},
            schema_metadata={},
            column_statistics=None,
            quality_metrics=None,
        )
        session = Mock(session_token="s", message_count=0)

        result = with_anton_context(None, dataset, session)

        assert "Recipient message:" in result
        # The user_message part after the colon should be empty
        after_colon = result.split("Recipient message:")[-1]
        assert after_colon.strip() == ""


# ── build_single_file_prompt ─────────────────────────────────────────

class TestBuildSingleFilePrompt:
    """build_single_file_prompt(dataset, file_upload, database_name, table_name)"""

    def test_basic_prompt(self):
        """Happy path: produces a prompt with dataset info and schema."""
        dataset = Mock(
            name="Sales Report",
            description="Q1 sales data",
            type=Mock(value="csv"),
            row_count=1000,
            column_count=8,
            schema_info={
                "columns": [
                    {"name": "date", "type": "date"},
                    {"name": "revenue", "type": "float"},
                    {"name": "region", "type": "text"},
                ]
            },
            ai_summary="Quarterly sales summary with regional breakdown",
        )
        file_upload = Mock(original_filename="sales_q1.csv")

        prompt = build_single_file_prompt(dataset, file_upload, "mindsdb_db", "sales_table")

        assert "Sales Report" in prompt
        assert "Q1 sales data" in prompt
        assert "sales_q1.csv" in prompt
        assert "mindsdb_db" in prompt
        assert "sales_table" in prompt
        assert "mindsdb_db.sales_table" in prompt
        assert "date: date" in prompt
        assert "revenue: float" in prompt
        assert "region: text" in prompt
        assert "Quarterly sales summary" in prompt
        assert "SELECT * FROM mindsdb_db.sales_table" in prompt

    def test_no_description(self):
        """Missing description shows fallback text."""
        dataset = Mock(
            name="No Desc",
            description=None,
            type=Mock(value="csv"),
            row_count=0,
            column_count=0,
            schema_info=None,
            ai_summary=None,
        )
        file_upload = Mock(original_filename="file.csv")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        assert "No description provided" in prompt
        assert "Unknown" in prompt  # row_count
        assert "Unknown" in prompt  # column_count

    def test_no_file_upload(self):
        """None file_upload shows 'Unknown'."""
        dataset = Mock(
            name="No File",
            description="No upload",
            type=Mock(value="csv"),
            row_count=10,
            column_count=3,
            schema_info=None,
            ai_summary=None,
        )

        prompt = build_single_file_prompt(dataset, None, "db", "table")

        assert "Unknown" in prompt  # original_filename

    def test_schema_limited_to_20_columns(self):
        """Only first 20 columns appear in schema, with truncation notice."""
        dataset = Mock(
            name="Wide Table",
            description="Has many columns",
            type=Mock(value="csv"),
            row_count=100,
            column_count=25,
            schema_info={
                "columns": [{"name": f"col_{i}", "type": "int"} for i in range(25)]
            },
            ai_summary=None,
        )
        file_upload = Mock(original_filename="wide.csv")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        # First 20 columns appear
        assert "col_0: int" in prompt
        assert "col_19: int" in prompt
        # Column 20+ should NOT appear
        assert "col_20: int" not in prompt
        # Truncation notice
        assert "5 more columns" in prompt

    def test_ai_summary_included(self):
        """AI summary is included when present."""
        dataset = Mock(
            name="Summary Test",
            description="Test",
            type=Mock(value="csv"),
            row_count=50,
            column_count=4,
            schema_info={"columns": [{"name": "x", "type": "int"}]},
            ai_summary="This dataset contains test data for validation purposes.",
        )
        file_upload = Mock(original_filename="test.csv")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        assert "Dataset Summary:" in prompt
        assert "test data for validation" in prompt

    def test_no_ai_summary(self):
        """When ai_summary is None, summary section is omitted."""
        dataset = Mock(
            name="No Summary",
            description="Test",
            type=Mock(value="csv"),
            row_count=10,
            column_count=2,
            schema_info={"columns": [{"name": "x", "type": "int"}]},
            ai_summary=None,
        )
        file_upload = Mock(original_filename="data.csv")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        assert "Dataset Summary:" not in prompt

    def test_type_enum_value(self):
        """Dataset type with .value attribute is handled."""
        dataset = Mock(
            name="Type Test",
            description="Test",
            type=Mock(value="excel"),
            row_count=10,
            column_count=2,
            schema_info=None,
            ai_summary=None,
        )
        file_upload = Mock(original_filename="data.xlsx")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        assert "excel" in prompt

    def test_type_string(self):
        """Dataset type as plain string is handled."""
        dataset = Mock(
            name="String Type",
            description="Test",
            type="json",
            row_count=10,
            column_count=2,
            schema_info=None,
            ai_summary=None,
        )
        file_upload = Mock(original_filename="data.json")

        prompt = build_single_file_prompt(dataset, file_upload, "db", "table")

        assert "json" in prompt


# ── build_multi_file_prompt ──────────────────────────────────────────

class TestBuildMultiFilePrompt:
    """build_multi_file_prompt(dataset, dataset_files, file_descriptions, all_tables)"""

    def test_basic_multi_file_prompt(self):
        """Happy path: produces a prompt describing multiple files."""
        dataset = Mock(
            name="Multi Sales",
            description="Multiple sales files",
            type=Mock(value="csv"),
            schema_info={
                "columns": [
                    {"name": "product", "type": "text"},
                    {"name": "sales", "type": "float"},
                ]
            },
            ai_summary="Combined sales analysis across regions",
        )
        files = [
            Mock(is_primary=True, filename="north.csv"),
            Mock(is_primary=False, filename="south.csv"),
        ]
        descriptions = ["Table: north_sales (north.csv)", "Table: south_sales (south.csv)"]
        tables = ["mindsdb.north_sales", "mindsdb.south_sales"]

        prompt = build_multi_file_prompt(dataset, files, descriptions, tables)

        assert "Multi Sales" in prompt
        assert "Multiple sales files" in prompt
        assert "MULTI-FILE" in prompt
        assert "2" in prompt  # total files
        assert "2" in prompt  # total tables
        assert "north.csv" in prompt
        assert "south.csv" in prompt
        assert "mindsdb.north_sales" in prompt
        assert "mindsdb.south_sales" in prompt
        assert "CROSS-FILE" in prompt
        assert "Combined sales analysis" in prompt

    def test_primary_file_schema(self):
        """Primary file schema is included."""
        dataset = Mock(
            name="Multi Schema",
            description="Schema test",
            type=Mock(value="csv"),
            schema_info={
                "columns": [
                    {"name": "id", "type": "int"},
                    {"name": "value", "type": "float"},
                ]
            },
            ai_summary=None,
        )
        files = [
            Mock(is_primary=True, filename="primary.csv"),
            Mock(is_primary=False, filename="other.csv"),
        ]

        prompt = build_multi_file_prompt(dataset, files, ["desc1", "desc2"], ["t1", "t2"])

        assert "Primary File Schema (primary.csv)" in prompt
        assert "id: int" in prompt
        assert "value: float" in prompt

    def test_no_primary_file_uses_first(self):
        """When no file is primary, the first file's schema is shown."""
        dataset = Mock(
            name="No Primary",
            description="No primary flag",
            type=Mock(value="csv"),
            schema_info={
                "columns": [{"name": "col", "type": "text"}]
            },
            ai_summary=None,
        )
        files = [
            Mock(is_primary=False, filename="first.csv"),
            Mock(is_primary=False, filename="second.csv"),
        ]

        prompt = build_multi_file_prompt(dataset, files, ["desc1", "desc2"], ["t1", "t2"])

        assert "Primary File Schema (first.csv)" in prompt

    def test_schema_limited_to_15_columns(self):
        """Only first 15 columns appear in multi-file schema."""
        dataset = Mock(
            name="Wide Multi",
            description="Many columns",
            type=Mock(value="csv"),
            schema_info={
                "columns": [{"name": f"col_{i}", "type": "int"} for i in range(20)]
            },
            ai_summary=None,
        )
        files = [Mock(is_primary=True, filename="primary.csv")]

        prompt = build_multi_file_prompt(dataset, files, ["desc"], ["t"])

        assert "col_0: int" in prompt
        assert "col_14: int" in prompt
        assert "col_15: int" not in prompt
        assert "5 more columns" in prompt

    def test_no_schema_info(self):
        """When schema_info is None or has no columns, schema section is omitted."""
        dataset = Mock(
            name="No Schema",
            description="No schema",
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary=None,
        )
        files = [Mock(is_primary=True, filename="data.csv")]

        prompt = build_multi_file_prompt(dataset, files, ["desc"], ["t"])

        assert "Primary File Schema" not in prompt

    def test_empty_schema_columns(self):
        """When schema_info has empty columns list, schema section shows no columns."""
        dataset = Mock(
            name="Empty Schema",
            description="Empty columns",
            type=Mock(value="csv"),
            schema_info={"columns": []},
            ai_summary=None,
        )
        files = [Mock(is_primary=True, filename="data.csv")]

        prompt = build_multi_file_prompt(dataset, files, ["desc"], ["t"])

        # The header is present but no column lines follow
        assert "Primary File Schema (data.csv):" in prompt
        # No individual column lines
        assert "Unknown:" not in prompt

    def test_ai_summary_included(self):
        """AI summary appears in multi-file prompt when present."""
        dataset = Mock(
            name="Summary Multi",
            description="Test",
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary="Cross-file analysis complete",
        )
        files = [Mock(is_primary=True, filename="a.csv")]

        prompt = build_multi_file_prompt(dataset, files, ["desc"], ["t"])

        assert "Dataset Summary:" in prompt
        assert "Cross-file analysis" in prompt

    def test_no_ai_summary(self):
        """When ai_summary is None, summary section omitted."""
        dataset = Mock(
            name="No Summary Multi",
            description="Test",
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary=None,
        )
        files = [Mock(is_primary=True, filename="a.csv")]

        prompt = build_multi_file_prompt(dataset, files, ["desc"], ["t"])

        assert "Dataset Summary:" not in prompt

    def test_empty_files_list(self):
        """Empty files list produces a valid prompt with 0 files."""
        dataset = Mock(
            name="Empty Multi",
            description="No files",
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary=None,
        )

        prompt = build_multi_file_prompt(dataset, [], [], [])

        assert "0" in prompt  # total files
        assert "Total Tables: 0" in prompt

    def test_cross_file_joins_mentioned(self):
        """Cross-file join examples appear in prompt."""
        dataset = Mock(
            name="Join Test",
            description="Cross-file test",
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary=None,
        )
        files = [
            Mock(is_primary=False, filename="weather.csv"),
            Mock(is_primary=False, filename="harvest.csv"),
        ]

        prompt = build_multi_file_prompt(dataset, files, ["desc1", "desc2"], ["t1", "t2"])

        assert "CROSS-FILE JOINS" in prompt
        assert "weather_data" in prompt
        assert "harvest_data" in prompt

    def test_type_enum_value(self):
        """Dataset type with .value attribute is handled."""
        dataset = Mock(
            name="Type Multi",
            description="Test",
            type=Mock(value="excel"),
            schema_info=None,
            ai_summary=None,
        )
        prompt = build_multi_file_prompt(dataset, [], [], [])
        assert "excel" in prompt

    def test_type_string(self):
        """Dataset type as plain string is handled."""
        dataset = Mock(
            name="String Type Multi",
            description="Test",
            type="json",
            schema_info=None,
            ai_summary=None,
        )
        prompt = build_multi_file_prompt(dataset, [], [], [])
        assert "json" in prompt

    def test_no_description(self):
        """Missing description shows fallback."""
        dataset = Mock(
            name="No Desc Multi",
            description=None,
            type=Mock(value="csv"),
            schema_info=None,
            ai_summary=None,
        )
        prompt = build_multi_file_prompt(dataset, [], [], [])
        assert "No description provided" in prompt
