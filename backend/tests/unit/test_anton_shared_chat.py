from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from app.api.data_sharing import (
    _attach_shared_chat_visualizations,
    _build_anton_shared_context,
    _is_visualization_prompt,
    _with_anton_context,
)
from app.models.dataset import Dataset, DatasetChatSession, DatasetType
from app.services.mindsdb import MindsDBService


def make_dataset(**overrides):
    dataset = Dataset(
        id=1,
        name="Revenue Metrics",
        description="Monthly revenue and customer metrics",
        type=DatasetType.CSV,
        owner_id=1,
        organization_id=1,
        public_share_enabled=True,
        share_token="share-token",
        ai_chat_enabled=True,
        allow_ai_chat=True,
        row_count=12,
        column_count=3,
        schema_metadata={
            "taxonomy": {"revenue": "Financial metric"},
            "canonical_definitions": {"revenue": "recognized monthly revenue"},
        },
        column_statistics={"revenue": {"type": "number"}},
        quality_metrics={"completeness": 1.0},
        chat_context={
            "anton_memory": {
                "rules": ["Always use recognized revenue for revenue questions"],
                "lessons": ["Month is the canonical time grain"],
                "topics": {"finance": "Revenue is reported monthly"},
                "skills": ["dashboard_summary: use for executive KPI dashboards"],
            },
            "semantic_layer": {"dimensions": ["month"], "measures": ["revenue"]},
        },
    )
    for key, value in overrides.items():
        setattr(dataset, key, value)
    return dataset


def make_session():
    return DatasetChatSession(
        id=10,
        dataset_id=1,
        session_token="session-token",
        share_token="share-token",
        message_count=2,
        is_active=True,
        ai_model_name="test-model",
    )


def test_visualization_prompt_detects_agentic_bi_requests():
    assert _is_visualization_prompt("Create a dashboard of revenue trends")
    assert _is_visualization_prompt("Show me a chart")
    assert not _is_visualization_prompt("What columns are available?")


def test_anton_context_includes_memory_taxonomy_and_rules():
    context = _build_anton_shared_context(
        make_dataset(),
        make_session(),
        "Create a dashboard of revenue trends",
    )

    assert "outcome-first BI agent" in context
    assert "Always use recognized revenue" in context
    assert "Month is the canonical time grain" in context
    assert "Financial metric" in context
    assert "recognized monthly revenue" in context
    assert "dashboard_summary" in context
    assert "Only analyze this shared dataset" in context


@pytest.mark.asyncio
async def test_attach_visualizations_adds_real_chart_payloads(monkeypatch):
    dataset = make_dataset()
    mindsdb_service = MindsDBService()
    df = pd.DataFrame({
        "month": pd.date_range("2026-01-01", periods=4, freq="MS"),
        "revenue": [100, 125, 150, 175],
        "segment": ["A", "A", "B", "B"],
    })

    async def load_dataset(_dataset, _db):
        return df

    monkeypatch.setattr(mindsdb_service, "_load_dataset_for_visualization", load_dataset)

    response = await _attach_shared_chat_visualizations(
        chat_response={"answer": "Here is the trend."},
        dataset=dataset,
        db=Mock(),
        message="Show revenue trend as a chart",
        mindsdb_service=mindsdb_service,
    )

    assert response["has_visualizations"] is True
    assert response["visualization_count"] > 0
    assert response["data_analysis"]["basic_stats"]["rows"] == 4
    assert response["source"] == "anton_shared_chat"


@pytest.mark.asyncio
async def test_attach_visualizations_keeps_normal_chat_without_charts(monkeypatch):
    mindsdb_service = MindsDBService()
    load_mock = Mock()
    monkeypatch.setattr(mindsdb_service, "_load_dataset_for_visualization", load_mock)

    response = await _attach_shared_chat_visualizations(
        chat_response={"answer": "The dataset has revenue columns."},
        dataset=make_dataset(),
        db=Mock(),
        message="What columns are available?",
        mindsdb_service=mindsdb_service,
    )

    assert response["has_visualizations"] is False
    assert response["visualization_count"] == 0
    load_mock.assert_not_called()


@pytest.mark.asyncio
async def test_attach_visualizations_does_not_break_answer_for_unsupported_data(monkeypatch):
    mindsdb_service = MindsDBService()

    async def load_dataset(_dataset, _db):
        return None

    monkeypatch.setattr(mindsdb_service, "_load_dataset_for_visualization", load_dataset)

    response = await _attach_shared_chat_visualizations(
        chat_response={"answer": "I can summarize the document."},
        dataset=make_dataset(type=DatasetType.PDF),
        db=Mock(),
        message="Show a chart for this data",
        mindsdb_service=mindsdb_service,
    )

    assert response["answer"] == "I can summarize the document."
    assert response["has_visualizations"] is False
    assert "not tabular enough" in response["visualization_message"]


def test_mindsdb_loader_uses_safe_connector_query(monkeypatch):
    dataset = make_dataset(
        connector_id=20,
        mindsdb_database="finance_db",
        mindsdb_table_name="monthly_revenue",
    )
    mindsdb_service = MindsDBService()
    result_df = pd.DataFrame({"month": ["Jan"], "revenue": [100]})

    query_result = SimpleNamespace(fetch=Mock(return_value=result_df))
    connection = SimpleNamespace(query=Mock(return_value=query_result))
    monkeypatch.setattr(mindsdb_service, "connection", connection)
    monkeypatch.setattr(mindsdb_service, "_connected", True)

    df = mindsdb_service._load_mindsdb_table_for_visualization(dataset)

    assert df.equals(result_df)
    connection.query.assert_called_once_with("SELECT * FROM finance_db.monthly_revenue LIMIT 10000")


def test_mindsdb_loader_rejects_unsafe_connector_identifiers(monkeypatch):
    dataset = make_dataset(
        connector_id=20,
        mindsdb_database="finance_db;drop",
        mindsdb_table_name="monthly_revenue",
    )
    mindsdb_service = MindsDBService()
    query_mock = Mock()
    connection = SimpleNamespace(query=query_mock)
    monkeypatch.setattr(mindsdb_service, "connection", connection)
    monkeypatch.setattr(mindsdb_service, "_connected", True)

    assert mindsdb_service._load_mindsdb_table_for_visualization(dataset) is None
    query_mock.assert_not_called()


@pytest.mark.asyncio
async def test_shared_visualization_allows_recipient_from_different_organization(monkeypatch):
    dataset = make_dataset(organization_id=100, share_token="org-a-token")
    session = make_session()
    session.share_token = "org-a-token"
    mindsdb_service = MindsDBService()
    df = pd.DataFrame({
        "month": pd.date_range("2026-01-01", periods=3, freq="MS"),
        "revenue": [200, 220, 260],
    })

    async def load_dataset(_dataset, _db):
        assert _dataset.organization_id == 100
        assert _dataset.share_token == "org-a-token"
        return df

    monkeypatch.setattr(mindsdb_service, "_load_dataset_for_visualization", load_dataset)

    response = await _attach_shared_chat_visualizations(
        chat_response={"answer": "Revenue is trending upward."},
        dataset=dataset,
        db=Mock(),
        message="Visualize revenue trend for this shared data",
        mindsdb_service=mindsdb_service,
    )
    prompt = _with_anton_context("Visualize revenue trend", dataset, session)

    assert response["has_visualizations"] is True
    assert response["data_analysis"]["dataset_name"] == "Revenue Metrics"
    assert "Only analyze this shared dataset" in prompt
    assert "org-a-token" not in response["answer"]


@pytest.mark.asyncio
async def test_shared_visualization_stays_scoped_to_requested_dataset(monkeypatch):
    requested_dataset = make_dataset(id=1, name="Org A Revenue", organization_id=100, share_token="token-a")
    other_dataset = make_dataset(id=2, name="Org B Revenue", organization_id=200, share_token="token-b")
    mindsdb_service = MindsDBService()
    loaded_dataset_ids = []

    async def load_dataset(dataset, _db):
        loaded_dataset_ids.append(dataset.id)
        return pd.DataFrame({"revenue": [10, 20, 30], "segment": ["A", "B", "C"]})

    monkeypatch.setattr(mindsdb_service, "_load_dataset_for_visualization", load_dataset)

    response = await _attach_shared_chat_visualizations(
        chat_response={"answer": "Here is the requested dataset chart."},
        dataset=requested_dataset,
        db=Mock(),
        message="Show a bar chart",
        mindsdb_service=mindsdb_service,
    )
    requested_prompt = _with_anton_context("Show a bar chart", requested_dataset, make_session())
    other_prompt = _with_anton_context("Show a bar chart", other_dataset, make_session())

    assert loaded_dataset_ids == [1]
    assert response["has_visualizations"] is True
    assert "Org A Revenue" in requested_prompt
    assert "Org B Revenue" in other_prompt
    assert "Org B Revenue" not in requested_prompt
