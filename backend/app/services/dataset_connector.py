"""
Entrust Data Sharing MCP Platform - Dataset Connector Service

Handles MindsDB connector creation, file uploads, and agent setup
for single-file and multi-file datasets.
Extracted from MindsDBService for focused responsibility.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.services.prompt_templates import build_single_file_prompt, build_multi_file_prompt

logger = logging.getLogger(__name__)


class DatasetConnectorService:
    """Service for MindsDB connector/agent setup operations.

    Depends on a MindsDB service (or AgentGateway-compatible object)
    for connection and agent lifecycle management.
    """

    def __init__(self, mindsdb_service):
        self._service = mindsdb_service

    # ------------------------------------------------------------------
    # Delegated helpers
    # ------------------------------------------------------------------

    @property
    def connection(self):
        return self._service.connection

    def ensure_connection(self) -> bool:
        return self._service.ensure_connection()

    def upload_file_to_mindsdb(self, full_path: str, file_name: str) -> Optional[str]:
        return self._service.upload_file_to_mindsdb(full_path, file_name)

    def is_supported_file_type(self, file_path: str) -> bool:
        return self._service.is_supported_file_type(file_path)

    def get_file_type(self, file_path: str) -> Optional[str]:
        return self._service.get_file_type(file_path)

    def create_file_database_connector(self, file_upload: "FileUpload") -> Dict[str, Any]:
        """Delegate to the parent service's implementation."""
        return self._service.create_file_database_connector(file_upload)

    def test_file_database_connector(self, database_name: str, file_upload: "FileUpload",
                                     uploaded_file_name: str = None) -> Dict[str, Any]:
        return self._service.test_file_database_connector(database_name, file_upload, uploaded_file_name)

    def delete_agent(self, agent_name: str) -> bool:
        return self._service.delete_agent(agent_name)

    def clear_dataset_agent_metadata(self, dataset, db) -> None:
        return self._service.clear_dataset_agent_metadata(dataset, db)

    # ------------------------------------------------------------------
    # Agent CRUD
    # ------------------------------------------------------------------

    def _create_agent_with_default_llm(self, agent_name: str, tables: List[str], prompt_template: str):
        """Create a MindsDB agent via REST API with default LLM configuration."""
        import requests
        payload = {
            "agent": {
                "name": agent_name,
                "data": {"tables": tables},
                "prompt_template": prompt_template,
                "params": {}
            }
        }
        response = requests.post(
            f"{self._service.base_url}/api/projects/mindsdb/agents",
            json=payload,
            timeout=120
        )
        if response.status_code == 409:
            return self.connection.agents.get(agent_name)
        response.raise_for_status()
        return self.connection.agents.get(agent_name)

    def create_or_get_agent(self, agent_name: str, tables: List[str], prompt_template: str,
                            model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create or retrieve an agent for a specific dataset."""
        if not self.ensure_connection():
            return {"success": False, "error": "Failed to connect to MindsDB"}

        try:
            # Try to get existing agent
            try:
                agent = self.connection.agents.get(agent_name)
                logger.info(f"✅ Retrieved existing agent: {agent_name}")
                return {
                    "success": True,
                    "agent": agent,
                    "agent_name": agent_name,
                    "status": "existing"
                }
            except Exception:
                logger.info(f"Agent {agent_name} not found, creating new one...")

            logger.info(f"🤖 Creating agent '{agent_name}' with {len(tables)} tables")
            logger.info("📡 Using MindsDB default LLM configuration")
            logger.debug(f"Agent tables: {tables}")

            agent = self._create_agent_with_default_llm(
                agent_name=agent_name,
                tables=tables,
                prompt_template=prompt_template
            )

            logger.info(f"✅ Created new agent: {agent_name}")
            return {
                "success": True,
                "agent": agent,
                "agent_name": agent_name,
                "status": "created"
            }

        except Exception as e:
            logger.error(f"❌ Failed to create/get agent {agent_name}: {e}")
            return {"success": False, "error": str(e)}

    def update_agent(self, agent_name: str, new_tables: List[str] = None,
                     new_prompt: str = None, new_model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update agent's data sources, prompt, or model configuration."""
        try:
            self.delete_agent(agent_name)
            logger.info(f"🔄 Agent {agent_name} deleted for recreation")
            return {
                "success": True,
                "message": f"Agent {agent_name} marked for recreation",
                "action": "recreate"
            }
        except Exception as e:
            logger.error(f"❌ Failed to update agent {agent_name}: {e}")
            return {"success": False, "error": str(e)}

    def delete_agent(self, agent_name: str) -> bool:
        """Delete agent when dataset is deleted or needs recreation."""
        import requests
        try:
            response = requests.delete(
                f"{self._service.base_url}/api/projects/mindsdb/agents/{agent_name}"
            )
            if response.status_code in [200, 204, 404]:
                logger.info(f"✅ Deleted agent: {agent_name}")
                return True
            else:
                logger.warning(f"⚠️ Failed to delete agent {agent_name}: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to delete agent {agent_name}: {e}")
            return False

    def clear_dataset_agent_metadata(self, dataset, db) -> None:
        dataset.agent_name = None
        dataset.agent_created_at = None
        dataset.agent_last_updated = None
        db.commit()

    def delete_dataset_agent(self, dataset, db) -> bool:
        agent_name = getattr(dataset, "agent_name", None)
        if not agent_name:
            return True
        deleted = self.delete_agent(agent_name)
        if deleted:
            self.clear_dataset_agent_metadata(dataset, db)
        return deleted

    def list_agents(self) -> List[str]:
        """List all available agents in MindsDB."""
        if not self.ensure_connection():
            return []
        try:
            agents = self.connection.agents.list()
            agent_names = [agent.name for agent in agents]
            logger.info(f"📋 Found {len(agent_names)} agents")
            return agent_names
        except Exception as e:
            logger.error(f"❌ Failed to list agents: {e}")
            return []

    # ------------------------------------------------------------------
    # Single-file agent setup
    # ------------------------------------------------------------------

    def setup_single_file_agent(self, dataset, db) -> Dict[str, Any]:
        """Create an agent for a single-file dataset."""
        try:
            logger.info(f"🔧 Setting up single-file agent for dataset: {dataset.name} (ID: {dataset.id})")

            agent_name = f"dataset_{dataset.id}_agent"

            # Check if agent already exists and is current
            if dataset.agent_name == agent_name and dataset.agent_created_at:
                logger.info(f"♻️  Agent already exists: {agent_name}")
                try:
                    agent = self.connection.agents.get(agent_name)
                    return {
                        "success": True,
                        "agent_name": agent_name,
                        "status": "existing",
                        "agent": agent
                    }
                except Exception:
                    logger.info(f"Agent {agent_name} not found in MindsDB, will recreate")

            # Get file upload record (if it exists)
            from app.models.file_handler import FileUpload
            file_upload = db.query(FileUpload).filter(
                FileUpload.dataset_id == dataset.id
            ).first()

            # Try to create connector either from FileUpload, connector metadata, or directly from dataset
            connector_result = None
            database_name = None
            table_name = "data"

            if file_upload:
                logger.info(f"📁 Using FileUpload record for dataset {dataset.id}")
                connector_result = self.create_file_database_connector(file_upload)
            elif dataset.connector_id and dataset.mindsdb_database and dataset.mindsdb_table_name:
                logger.info(f"🔌 Using connector-backed MindsDB table for dataset {dataset.id}")
                connector_result = {
                    "success": True,
                    "database_name": dataset.mindsdb_database,
                    "test_result": {"table_name": dataset.mindsdb_table_name}
                }
            elif dataset.file_path or dataset.source_url:
                logger.info(f"📁 Creating connector from dataset file_path for dataset {dataset.id}")
                file_path = dataset.file_path or dataset.source_url

                if file_path and not any(file_path.lower().endswith(ext) for ext in
                                         ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']):
                    try:
                        from app.models.dataset import DatasetFile
                        dataset_files = db.query(DatasetFile).filter(
                            DatasetFile.dataset_id == dataset.id,
                            DatasetFile.is_deleted == False
                        ).all()

                        if dataset_files:
                            dataset_file = dataset_files[0]
                            database_name = f"dataset_{dataset.id}_db"

                            if self.ensure_connection():
                                try:
                                    self.connection.databases.create(
                                        name=database_name,
                                        engine='files'
                                    )
                                    logger.info(f"✅ Created MindsDB database: {database_name}")
                                except Exception as e:
                                    logger.info(f"Database {database_name} may already exist: {e}")

                                connector_result = {
                                    "success": True,
                                    "database_name": database_name,
                                    "test_result": {"table_name": table_name}
                                }
                    except Exception as e:
                        logger.warning(f"Could not create connector from dataset file: {e}")

            if not connector_result or not connector_result.get("success"):
                connector_error = connector_result.get("error") if connector_result else None
                return {
                    "success": False,
                    "error": connector_error or "No valid file upload or file path found for dataset, or dataset is not a data file (e.g., image)"
                }

            database_name = connector_result["database_name"]
            table_name = connector_result.get("test_result", {}).get("table_name", "data")
            full_table_ref = f"{database_name}.{table_name}"

            logger.info(f"📊 Using table: {full_table_ref}")

            # Build comprehensive prompt template
            prompt_template = build_single_file_prompt(dataset, file_upload, database_name, table_name)

            # Create or get agent
            agent_result = self.create_or_get_agent(
                agent_name=agent_name,
                tables=[full_table_ref],
                prompt_template=prompt_template
            )

            if not agent_result.get("success"):
                return agent_result

            # Update dataset with agent info
            dataset.agent_name = agent_name
            dataset.agent_created_at = datetime.utcnow()
            dataset.agent_last_updated = datetime.utcnow()
            db.commit()

            logger.info(f"✅ Single-file agent setup complete: {agent_name}")

            return {
                "success": True,
                "agent_name": agent_name,
                "table": full_table_ref,
                "status": agent_result.get("status", "created"),
                "agent": agent_result.get("agent")
            }

        except Exception as e:
            logger.error(f"❌ Failed to setup single-file agent: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Multi-file agent setup
    # ------------------------------------------------------------------

    def setup_multi_file_agent(self, dataset, db) -> Dict[str, Any]:
        """Create an agent that can query ALL files in a multi-file dataset."""
        try:
            logger.info(f"🔧 Setting up MULTI-FILE agent for dataset: {dataset.name} (ID: {dataset.id})")

            if not dataset.is_multi_file_dataset:
                return {"success": False, "error": "Dataset is not a multi-file dataset"}

            agent_name = f"dataset_{dataset.id}_multi_agent"

            # Check if agent already exists and is current
            if dataset.agent_name == agent_name and dataset.agent_created_at:
                logger.info(f"♻️  Multi-file agent already exists: {agent_name}")
                try:
                    agent = self.connection.agents.get(agent_name)
                    return {
                        "success": True,
                        "agent_name": agent_name,
                        "status": "existing",
                        "agent": agent
                    }
                except Exception:
                    logger.info(f"Agent {agent_name} not found in MindsDB, will recreate")

            # Get ALL files in the dataset
            from app.models.dataset import DatasetFile
            dataset_files = db.query(DatasetFile).filter(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.is_deleted == False
            ).all()

            if not dataset_files:
                return {"success": False, "error": "No files found in multi-file dataset"}

            logger.info(f"📁 Found {len(dataset_files)} files to include in agent")

            # Create database connector for EACH file and collect table references
            all_tables = []
            file_descriptions = []
            from app.models.file_handler import FileUpload

            for idx, dataset_file in enumerate(dataset_files, 1):
                logger.info(f"  Processing file {idx}/{len(dataset_files)}: {dataset_file.filename}")

                file_upload = db.query(FileUpload).filter(
                    FileUpload.dataset_id == dataset.id,
                    FileUpload.original_filename == dataset_file.filename
                ).first()

                if not file_upload:
                    logger.warning(f"  ⚠️  No upload record found for {dataset_file.filename}, skipping")
                    continue

                connector_result = self.create_file_database_connector(file_upload)

                if connector_result.get("success"):
                    uploaded_filename = connector_result.get("uploaded_filename")
                    if uploaded_filename:
                        full_table_ref = f"files.{uploaded_filename}"
                    else:
                        database_name = connector_result["database_name"]
                        table_name = connector_result.get("test_result", {}).get("table_name", "data")
                        full_table_ref = f"{database_name}.{table_name}"

                    all_tables.append(full_table_ref)

                    file_type = dataset_file.file_type or "Unknown"
                    is_primary = "PRIMARY" if dataset_file.is_primary else "Supporting"
                    file_descriptions.append(
                        f"  - {full_table_ref}: {dataset_file.filename} ({file_type}, {is_primary})"
                    )

                    logger.info(f"    ✅ Added table: {full_table_ref}")
                else:
                    logger.warning(f"  ⚠️  Failed to create connector for {dataset_file.filename}")

            if not all_tables:
                return {"success": False, "error": "Failed to create database connectors for any files"}

            logger.info(f"📊 Agent will have access to {len(all_tables)} tables")

            # Build comprehensive multi-file prompt template
            prompt_template = build_multi_file_prompt(
                dataset, dataset_files, file_descriptions, all_tables
            )

            # Create or get agent with ALL tables
            agent_result = self.create_or_get_agent(
                agent_name=agent_name,
                tables=all_tables,
                prompt_template=prompt_template
            )

            if not agent_result.get("success"):
                return agent_result

            # Update dataset with agent info
            dataset.agent_name = agent_name
            dataset.agent_created_at = datetime.utcnow()
            dataset.agent_last_updated = datetime.utcnow()
            db.commit()

            logger.info(f"✅ Multi-file agent setup complete: {agent_name} with {len(all_tables)} tables")

            return {
                "success": True,
                "agent_name": agent_name,
                "tables": all_tables,
                "tables_count": len(all_tables),
                "files_count": len(dataset_files),
                "status": agent_result.get("status", "created"),
                "agent": agent_result.get("agent")
            }

        except Exception as e:
            logger.error(f"❌ Failed to setup multi-file agent: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
