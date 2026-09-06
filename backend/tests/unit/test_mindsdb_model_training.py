"""Unit tests for MindsDBService model training methods.

Tests the real MindsDBService instance with the raw-SDK seam pattern
(monkeypatch the .connection attribute) to assert exact SQL generation
without a live MindsDB server.

See test_anton_shared_chat.py for the canonical pattern this follows.
"""

from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock

import pandas as pd
import pytest
from _pytest.monkeypatch import MonkeyPatch

from app.services.mindsdb import MindsDBService


# ── Fixtures ──


@pytest.fixture
def svc() -> MindsDBService:
    """Real MindsDBService with faked connection and _connected guard."""
    s = MindsDBService()
    return s


@pytest.fixture
def patched_svc(svc: MindsDBService, monkeypatch: MonkeyPatch):
    """Patched MindsDBService whose .connection.query returns a mock.

    The returned fixture exposes `query_mock` so tests can assert call args.
    """
    query_mock = Mock()
    monkeypatch.setattr(svc, "connection", SimpleNamespace(query=query_mock))
    monkeypatch.setattr(svc, "_connected", True)
    # Return both via a namespace
    ns = SimpleNamespace(svc=svc, query_mock=query_mock)
    return ns


def _fetch_result(df: pd.DataFrame) -> SimpleNamespace:
    """Build a MindsDB SDK result object that returns *df* from .fetch()."""
    return SimpleNamespace(fetch=Mock(return_value=df))


# ── get_models ──


class TestGetModels:
    """MindsDBService.get_models()"""

    def test_returns_rows(self, patched_svc):
        """SELECT * FROM mindsdb.models returns the rows list."""
        df = pd.DataFrame([
            {"name": "m1", "engine": "lightgbm", "status": "complete", "predict": "yield"},
            {"name": "m2", "engine": "neural", "status": "training", "predict": "price"},
        ])
        patched_svc.query_mock.return_value = _fetch_result(df)
        result = patched_svc.svc.get_models()
        assert result == [
            {"name": "m1", "engine": "lightgbm", "status": "complete", "predict": "yield"},
            {"name": "m2", "engine": "neural", "status": "training", "predict": "price"},
        ]
        patched_svc.query_mock.assert_called_once_with("SELECT * FROM mindsdb.models")

    def test_empty_when_no_rows(self, patched_svc):
        """Empty DataFrame returns empty list."""
        df = pd.DataFrame(columns=["name"])
        patched_svc.query_mock.return_value = _fetch_result(df)
        assert patched_svc.svc.get_models() == []

    def test_error_returns_empty_list(self, patched_svc):
        """When execute_query returns an error dict, returns []."""
        # Bypass execute_query and test the underlying SQL path
        patched_svc.query_mock.return_value = SimpleNamespace(fetch=Mock(return_value=None))
        result = patched_svc.svc.get_models()
        assert result == []


# ── create_model ──


class TestCreateModel:
    """MindsDBService.create_model()"""

    def test_basic_create(self, patched_svc):
        """CREATE MODEL with minimal args."""
        patched_svc.query_mock.return_value = _fetch_result(pd.DataFrame())
        result = patched_svc.svc.create_model(
            model_name="m1",
            query="SELECT * FROM files.data",
            engine="files",
            predict="yield",
        )
        assert result["status"] == "success"
        call_sql = patched_svc.query_mock.call_args[0][0]
        assert "CREATE MODEL" in call_sql
        assert "m1" in call_sql
        assert "FROM files (SELECT * FROM files.data)" in call_sql
        assert "PREDICT `yield`" in call_sql

    def test_create_with_options(self, patched_svc):
        """CREATE MODEL WITH options appended."""
        patched_svc.query_mock.return_value = _fetch_result(pd.DataFrame())
        patched_svc.svc.create_model(
            model_name="m2",
            query="SELECT * FROM db.table",
            engine="mindsdb",
            predict="target",
            options={"using": "{\"task\": \"regression\"}"},
        )
        call_sql = patched_svc.query_mock.call_args[0][0]
        assert "WITH" in call_sql
        assert 'using' in call_sql

    def test_unsafe_name_raises(self, svc, monkeypatch):
        """Identifiers that fail is_safe_mindsdb_identifier raise ValueError."""
        monkeypatch.setattr(svc, "_connected", True)
        monkeypatch.setattr(svc, "connection", SimpleNamespace(query=Mock()))
        monkeypatch.setattr(svc, "is_safe_mindsdb_identifier", Mock(return_value=False))
        with pytest.raises(ValueError, match="Unsafe"):
            svc.create_model(model_name="bad name", query="SELECT 1", engine="mindsdb", predict="col")


# ── get_model_info ──


class TestGetModelInfo:
    """MindsDBService.get_model_info()"""

    def test_returns_first_row(self, patched_svc):
        """Returns the first row dict when model exists."""
        df = pd.DataFrame([
            {"name": "m1", "status": "completed", "accuracy": "{'r2': 0.9}"},
        ])
        patched_svc.query_mock.return_value = _fetch_result(df)
        result = patched_svc.svc.get_model_info("m1")
        assert result == {"name": "m1", "status": "completed", "accuracy": "{'r2': 0.9}"}
        patched_svc.query_mock.assert_called_once_with(
            "SELECT * FROM mindsdb.models WHERE name = 'm1'"
        )

    def test_returns_none_when_not_found(self, patched_svc):
        """Empty result returns None."""
        df = pd.DataFrame(columns=["name", "status"])
        patched_svc.query_mock.return_value = _fetch_result(df)
        assert patched_svc.svc.get_model_info("nonexistent") is None

    def test_unsafe_name_raises(self, svc, monkeypatch):
        """Unsafe identifier in model_name raises ValueError."""
        monkeypatch.setattr(svc, "_connected", True)
        monkeypatch.setattr(svc, "connection", SimpleNamespace(query=Mock()))
        monkeypatch.setattr(svc, "is_safe_mindsdb_identifier", Mock(return_value=False))
        with pytest.raises(ValueError, match="Unsafe"):
            svc.get_model_info("drop tables")


# ── predict ──


class TestPredict:
    """MindsDBService.predict()"""

    def test_returns_rows(self, patched_svc):
        """SELECT * FROM model WHERE conditions returns prediction rows."""
        df = pd.DataFrame([{"yield": 5.2, "confidence": 0.95}])
        patched_svc.query_mock.return_value = _fetch_result(df)
        result = patched_svc.svc.predict("m1", {"year": 2024, "crop": "corn"})
        assert result == [{"yield": 5.2, "confidence": 0.95}]
        call_sql = patched_svc.query_mock.call_args[0][0]
        assert "SELECT * FROM mindsdb.m1" in call_sql
        assert "year = 2024" in call_sql
        assert "crop = 'corn'" in call_sql

    def test_returns_empty_on_empty_result(self, patched_svc):
        """Empty prediction result returns empty list."""
        df = pd.DataFrame(columns=["yield"])
        patched_svc.query_mock.return_value = _fetch_result(df)
        assert patched_svc.svc.predict("m1", {"x": 1}) == []

    def test_sql_injection_escaping(self, patched_svc):
        """String values with single quotes are escaped."""
        df = pd.DataFrame([{"result": "ok"}])
        patched_svc.query_mock.return_value = _fetch_result(df)
        patched_svc.svc.predict("m1", {"name": "O'Brien"})
        call_sql = patched_svc.query_mock.call_args[0][0]
        assert "O''Brien" in call_sql

    def test_unsafe_name_raises(self, svc, monkeypatch):
        """Unsafe model_name raises ValueError."""
        monkeypatch.setattr(svc, "_connected", True)
        monkeypatch.setattr(svc, "connection", SimpleNamespace(query=Mock()))
        monkeypatch.setattr(svc, "is_safe_mindsdb_identifier", Mock(return_value=False))
        with pytest.raises(ValueError, match="Unsafe"):
            svc.predict("bad; name", {"x": 1})


# ── delete_model ──


class TestDeleteModel:
    """MindsDBService.delete_model()"""

    def test_drop_model_success(self, patched_svc):
        """DROP MODEL IF EXISTS returns True on success."""
        patched_svc.query_mock.return_value = _fetch_result(pd.DataFrame())
        result = patched_svc.svc.delete_model("m1")
        assert result is True
        patched_svc.query_mock.assert_called_once_with(
            "DROP MODEL IF EXISTS mindsdb.m1"
        )

    def test_unsafe_name_raises(self, svc, monkeypatch):
        """Unsafe model_name raises ValueError."""
        monkeypatch.setattr(svc, "_connected", True)
        monkeypatch.setattr(svc, "connection", SimpleNamespace(query=Mock()))
        monkeypatch.setattr(svc, "is_safe_mindsdb_identifier", Mock(return_value=False))
        with pytest.raises(ValueError, match="Unsafe"):
            svc.delete_model("bad; name")


# ── _format_sql_literal ──


class TestFormatSqlLiteral:
    """MindsDBService._format_sql_literal() helper."""

    def test_string(self, svc):
        assert svc._format_sql_literal("hello") == "'hello'"

    def test_string_with_quote(self, svc):
        assert svc._format_sql_literal("O'Brien") == "'O''Brien'"

    def test_none(self, svc):
        assert svc._format_sql_literal(None) == "NULL"

    def test_bool_true(self, svc):
        assert svc._format_sql_literal(True) == "True"

    def test_bool_false(self, svc):
        assert svc._format_sql_literal(False) == "False"

    def test_int(self, svc):
        assert svc._format_sql_literal(42) == "42"

    def test_float(self, svc):
        assert svc._format_sql_literal(3.14) == "3.14"
