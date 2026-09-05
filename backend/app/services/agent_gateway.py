"""
AgentGateway — abstract interface for AI agent operations.

Deep module boundary: consumers depend on this small protocol instead of
the full MindsDBService implementation.  This makes substitution (fake,
alternative provider) straightforward.
"""
from typing import Any, Dict, List, Optional, Protocol

from pandas import DataFrame


class AgentGateway(Protocol):
    """Small, stable interface for AI agent operations.

    Concrete implementations (MindsDBService, fakes, etc.) fulfil this protocol.
    """

    # ── Connection & health ──────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        ...

    def execute_query(self, query: str) -> Dict[str, Any]:
        ...

    def execute_raw_query(self, query: str):
        """Execute a raw SQL query and return the raw result object.

        This is a lower-level escape hatch for callers that need direct
        access to the MindsDB query result object (e.g. for DataFrame
        manipulation).  Most callers should use execute_query() instead.
        """
        ...

    def ensure_connection(self) -> bool:
        """Ensure the underlying connection is established."""
        ...

    # ── Agent lifecycle ──────────────────────────────────────────────

    def create_or_get_agent(
        self,
        agent_name: str,
        tables: List[str],
        prompt_template: str,
        model_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    def delete_agent(self, agent_name: str) -> bool:
        ...

    def delete_dataset_agent(self, dataset, db) -> bool:
        ...

    def list_agents(self) -> List[str]:
        ...

    # ── Dataset agent setup ──────────────────────────────────────────

    def setup_single_file_agent(self, dataset, db) -> Dict[str, Any]:
        ...

    def setup_multi_file_agent(self, dataset, db) -> Dict[str, Any]:
        ...

    # ── Chat ─────────────────────────────────────────────────────────

    async def chat_with_dataset_agent(
        self,
        dataset_id: int,
        message: str,
        db,
        session_id: str = None,
        stream: bool = True,
    ) -> Dict[str, Any]:
        ...

    async def chat_with_dataset(
        self,
        dataset_id: str,
        message: str,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        organization_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        ...

    # ── File management ──────────────────────────────────────────────

    def is_supported_file_type(self, file_path: str) -> bool:
        ...

    def get_file_type(self, file_path: str) -> Optional[str]:
        ...

    def upload_file_to_mindsdb(self, full_path: str, file_name: str) -> Optional[str]:
        ...

    def delete_file_from_mindsdb(self, file_name: str) -> bool:
        ...

    def delete_database_connector(self, database_name: str) -> bool:
        ...

    # ── Connector management ─────────────────────────────────────────

    def create_web_connector(
        self,
        connector_name: str,
        source_url: str,
        source_type: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        method: str = "GET",
    ) -> Dict[str, Any]:
        ...

    def test_web_connector(self, connector_name: str) -> Dict[str, Any]:
        ...

    def create_dataset_from_web_connector(
        self,
        dataset_name: str,
        connector_name: str,
        query: str,
        connection_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    def create_file_database_connector(self, file_upload) -> Dict[str, Any]:
        ...

    # ── Dataset helpers ──────────────────────────────────────────────

    def create_dataset_connection(
        self, dataset_name: str, file_url: str, file_type: str = "csv",
    ) -> Dict[str, Any]:
        ...

    def query_dataset(self, dataset_name: str, query: str) -> Dict[str, Any]:
        ...

    def is_safe_mindsdb_identifier(self, identifier: Optional[str]) -> bool:
        """Check whether *identifier* is safe for use in SQL identifiers."""
        ...

    def load_dataset_for_visualization(self, dataset, db):
        """Load dataset data into a DataFrame for visualization (async)."""
        ...

    def process_file_content(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """Extract content and metadata from a file (pdf/json) for preview."""
        ...

    # ── Deprecated backward-compat aliases (will be removed) ─────────

    def _is_safe_mindsdb_identifier(self, identifier: Optional[str]) -> bool:
        """Deprecated: use is_safe_mindsdb_identifier() instead."""
        ...