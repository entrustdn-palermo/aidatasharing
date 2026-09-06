"""
Entrust Data Sharing MCP Platform - MindsDB Agent Service

This service implements the agent-based architecture for data interactions.
The platform exclusively uses MindsDB agents for all AI-powered features.

Architecture:
- Chat with datasets is handled by MindsDB agents
- Supported file types: CSV, XLSX, XLS, JSON, TXT, PDF, Parquet
- Agents are configured and managed through MindsDB SDK
- All LLM interactions go through MindsDB's pre-configured models

Features:
- Single-file dataset agents
- Multi-file dataset agents with multiple table access
- Automatic file upload and database connector creation
- Persistent agent management with database tracking
"""

import mindsdb_sdk
from typing import Dict, List, Optional, Any
from app.core.config import settings
from app.core.app_config import get_app_config
import logging
import json
import os
from datetime import datetime
import requests
import pandas as pd
import io
import re

# Import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.file_handler import FileUpload

from app.services.pdf_processing import PDFProcessingService
from app.services.prompt_templates import build_single_file_prompt, build_multi_file_prompt
from app.services.chat_agent import ChatAgentService, clean_agent_answer, build_dataset_summary_answer
from app.services.dataset_connector import DatasetConnectorService

logger = logging.getLogger(__name__)


def _count_json_elements(obj) -> int:
    """Count top-level elements in a JSON structure."""
    if isinstance(obj, dict):
        return sum(_count_json_elements(v) for v in obj.values()) + len(obj)
    elif isinstance(obj, list):
        return sum(_count_json_elements(item) for item in obj) + len(obj)
    return 1


def _records_from_df(df: pd.DataFrame) -> list:
    """Convert a DataFrame to a list of dicts with numpy types handled."""
    if df is None or df.empty:
        return []
    import numpy as np
    records = df.to_dict(orient="records")
    # Convert numpy types in-place
    def _convert(v):
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.bool_):
            return bool(v)
        return v
    return [{k: _convert(v) for k, v in row.items()} for row in records]


class MindsDBService:
    # Supported file extensions for MindsDB agents
    SUPPORTED_FILE_EXTENSIONS = {
        '.csv': 'csv',
        '.json': 'json',
        '.xlsx': 'excel',
        '.xls': 'excel',
        '.parquet': 'parquet',
        '.txt': 'text',
        '.pdf': 'pdf'
    }

    def __init__(self):
        """
        Initialize MindsDB Service for Entrust MCP Platform.
        Now focused on agent-based architecture exclusively.
        """
        # Get centralized configuration
        self.app_config = get_app_config()

        # MindsDB connection settings
        self.base_url = self.app_config.services.get_mindsdb_url()

        # API keys (used by MindsDB agents, not directly by this service)
        self.api_key = self.app_config.integrations.GOOGLE_API_KEY

        # Debug log the API key (masked for security)
        if self.api_key:
            masked_key = self.api_key[:4] + "..." + self.api_key[-4:] if len(self.api_key) > 8 else "***"
            logger.info(f"✅ API key loaded for MindsDB agents: {masked_key}")
        else:
            logger.warning("⚠️ No API key found - MindsDB agents may not function")
            # Try to load directly from environment
            import os
            self.api_key = os.environ.get("GOOGLE_API_KEY")
            if self.api_key:
                masked_key = self.api_key[:4] + "..." + self.api_key[-4:] if len(self.api_key) > 8 else "***"
                logger.info(f"✅ API key loaded from environment for MindsDB agents: {masked_key}")
            else:
                logger.error("❌ No API key found - MindsDB agents will not be able to use LLMs")

        # Agent creation omits model fields so MindsDB uses its configured default LLM.
        self.agent_model = settings.MINDSDB_AGENT_MODEL or "mindsdb_default_llm"
        logger.info(f"🤖 MindsDB Agent model source: {self.agent_model}")

        # Connection state
        self.connection = None
        self._connected = False

        # Delegate services
        self._connector_service = DatasetConnectorService(self)
        self._chat_agent_service = ChatAgentService(self, self.agent_model)

        logger.info("✅ MindsDB Service initialized in agent-based mode")

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def ensure_connection(self) -> bool:
        """Ensure MindsDB SDK connection is established."""
        if self._connected and self.connection:
            return True

        try:
            logger.info(f"🔗 Connecting to MindsDB SDK at {self.base_url}")
            self.connection = mindsdb_sdk.connect(self.base_url)

            # Ensure we're using the mindsdb project
            try:
                self.connection.query("USE mindsdb")
                logger.info(f"✅ Using mindsdb project")
            except Exception as e:
                logger.warning(f"⚠️ Could not set mindsdb project: {e}")

            self._connected = True
            logger.info(f"✅ Connected to MindsDB SDK at {self.base_url}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to MindsDB: {e}")
            self._connected = False
            return False

    def _ensure_connection(self) -> bool:
        """Deprecated: use ensure_connection() instead."""
        return self.ensure_connection()

    # ------------------------------------------------------------------
    # Health & queries
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Perform health check of MindsDB service."""
        try:
            if not self.ensure_connection():
                return {"status": "error", "connection": "failed"}

            # Try to execute a simple query to test connection
            try:
                # Use raw SQL query instead of SDK methods
                result = self.connection.query("SELECT 1 as test")
                df = result.fetch()

                if not df.empty:
                    logger.info("🏥 Health check completed successfully")
                    return {
                        "status": "healthy",
                        "connection": "connected",
                        "engine_status": "accessible",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:
                    raise Exception("Empty result from health check query")

            except Exception as e:
                logger.warning(f"Health check query failed: {e}")
                return {
                    "status": "partial",
                    "connection": "connected",
                    "engine_status": "unknown",
                    "warning": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {
                "status": "error",
                "connection": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a SQL query on MindsDB and return results"""
        try:
            if not self.ensure_connection():
                return {"status": "error", "error": "MindsDB connection not available"}

            logger.info(f"🔍 Executing query: {query}")

            result = self.connection.query(query)

            if result and hasattr(result, 'fetch'):
                df = result.fetch()
                # Handle case where fetch() returns None
                if df is not None and hasattr(df, 'empty'):
                    return {
                        "status": "success",
                        "rows": _records_from_df(df) if not df.empty else [],
                        "columns": list(df.columns) if not df.empty else [],
                        "row_count": len(df)
                    }
                else:
                    # For DDL queries (CREATE, DROP, etc.) that don't return data
                    logger.info("✅ Query executed successfully (no data returned)")
                    return {
                        "status": "success",
                        "rows": [],
                        "columns": [],
                        "row_count": 0,
                        "message": "Query executed successfully"
                    }
            else:
                # For queries that don't have fetch method or return None
                logger.info("✅ Query executed successfully (no result object)")
                return {
                    "status": "success",
                    "rows": [],
                    "columns": [],
                    "row_count": 0,
                    "message": "Query executed successfully"
                }

        except Exception as e:
            logger.error(f"❌ Query execution failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def execute_raw_query(self, query: str):
        """Execute a raw SQL query and return the raw result object.

        This is a lower-level escape hatch for callers that need direct
        access to the MindsDB query result object (e.g. for DataFrame
        manipulation).  Most callers should use execute_query() instead.
        """
        if not self.ensure_connection():
            return None
        return self.connection.query(query)

    # ------------------------------------------------------------------
    # Dataset connections
    # ------------------------------------------------------------------

    def create_dataset_connection(self, dataset_name: str, file_url: str, file_type: str = "csv") -> Dict[str, Any]:
        """Create a dataset connection in MindsDB using a file URL."""
        try:
            if not self.ensure_connection():
                return {"status": "error", "message": "MindsDB connection not available"}

            # Sanitize dataset name for SQL
            safe_dataset_name = dataset_name.replace(" ", "_").replace("-", "_")
            safe_dataset_name = "".join(c for c in safe_dataset_name if c.isalnum() or c == "_")

            logger.info(f"🔗 Creating dataset connection: {safe_dataset_name} from {file_url}")

            # Create dataset from URL
            if file_type.lower() in ["csv", "json"]:
                create_query = f"""
                CREATE OR REPLACE DATASOURCE {safe_dataset_name}_datasource (
                    url '{file_url}',
                    type '{file_type.lower()}'
                )
                """
            else:
                # For other file types, create a generic datasource
                create_query = f"""
                CREATE OR REPLACE DATASOURCE {safe_dataset_name}_datasource (
                    url '{file_url}'
                )
                """

            logger.info(f"🔍 Executing dataset creation query: {create_query}")
            result = self.connection.query(create_query)

            return {
                "status": "success",
                "message": f"Dataset connection created: {safe_dataset_name}_datasource",
                "dataset_name": safe_dataset_name,
                "datasource_name": f"{safe_dataset_name}_datasource",
                "file_url": file_url
            }

        except Exception as e:
            logger.error(f"❌ Dataset connection creation failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to create dataset connection: {str(e)}"
            }

    def query_dataset(self, dataset_name: str, query: str) -> Dict[str, Any]:
        """Execute a query against a dataset in MindsDB."""
        try:
            if not self.ensure_connection():
                return {"status": "error", "message": "MindsDB connection not available"}

            safe_dataset_name = dataset_name.replace(" ", "_").replace("-", "_")
            safe_dataset_name = "".join(c for c in safe_dataset_name if c.isalnum() or c == "_")

            # Replace dataset placeholders in query
            formatted_query = query.replace("{dataset}", f"{safe_dataset_name}_datasource")

            logger.info(f"🔍 Executing dataset query: {formatted_query}")
            result = self.connection.query(formatted_query)

            if result and hasattr(result, 'fetch'):
                df = result.fetch()
                if df is not None and hasattr(df, 'empty'):
                    return {
                        "status": "success",
                        "rows": _records_from_df(df) if not df.empty else [],
                        "columns": list(df.columns) if not df.empty else [],
                        "row_count": len(df)
                    }

            return {
                "status": "success",
                "message": "Query executed successfully",
                "rows": [],
                "columns": [],
                "row_count": 0
            }

        except Exception as e:
            logger.error(f"❌ Dataset query failed: {str(e)}")
            return {
                "status": "error",
                "message": f"Query failed: {str(e)}"
            }

    # ------------------------------------------------------------------
    # Web connectors
    # ------------------------------------------------------------------

    def create_web_connector(
        self,
        connector_name: str,
        base_url: str,
        endpoint: str = "",
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        auth_config: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Create a MindsDB web connector for API endpoints."""
        try:
            if not self.ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Clean connector name for MindsDB
            clean_name = connector_name.lower().replace(' ', '_').replace('-', '_')

            # Build the full URL
            full_url = f"{base_url.rstrip('/')}{endpoint}"

            # Prepare connection parameters
            connection_params = {
                "url": full_url,
                "method": method.upper()
            }

            # Add headers if provided
            if headers:
                connection_params["headers"] = headers

            # Add authentication if provided
            if auth_config:
                if auth_config.get("api_key"):
                    if auth_config.get("auth_header"):
                        connection_params["headers"] = connection_params.get("headers", {})
                        connection_params["headers"][auth_config["auth_header"]] = auth_config["api_key"]
                    else:
                        connection_params["headers"] = connection_params.get("headers", {})
                        connection_params["headers"]["Authorization"] = f"Bearer {auth_config['api_key']}"

            # Create the web connector using MindsDB SQL
            create_connector_sql = f"""
            CREATE DATABASE IF NOT EXISTS {clean_name}
            WITH ENGINE = 'web',
            PARAMETERS = {json.dumps(connection_params)};
            """

            logger.info(f"🔗 Creating web connector: {clean_name}")
            logger.info(f"📄 SQL: {create_connector_sql}")

            try:
                result = self.connection.query(create_connector_sql)
                logger.info(f"✅ Web connector {clean_name} created successfully")

                # Test the connector by trying to fetch data
                test_result = self.test_web_connector(clean_name)

                return {
                    "success": True,
                    "connector_name": clean_name,
                    "database_name": clean_name,
                    "url": full_url,
                    "method": method,
                    "test_result": test_result,
                    "working_table_name": test_result.get("table_name", "data"),  # Pass working table name
                    "message": f"Web connector {clean_name} created successfully"
                }

            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"✅ Web connector {clean_name} already exists")
                    return {
                        "success": True,
                        "connector_name": clean_name,
                        "database_name": clean_name,
                        "url": full_url,
                        "method": method,
                        "message": f"Web connector {clean_name} already exists"
                    }
                else:
                    raise e

        except Exception as e:
            logger.error(f"❌ Failed to create web connector {connector_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "connector_name": connector_name
            }

    def test_web_connector(self, connector_name: str) -> Dict[str, Any]:
        """Test a web connector by fetching sample data."""
        try:
            if not self.ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # For web connectors, first check what tables are available
            table_name = "data"  # Default table name for web connectors
            try:
                show_tables_query = f"SHOW TABLES FROM {connector_name}"
                logger.info(f"🔍 Checking available tables: {show_tables_query}")
                tables_result = self.connection.query(show_tables_query)

                if tables_result and hasattr(tables_result, 'fetch'):
                    tables_df = tables_result.fetch()
                    logger.info(f"📊 Tables result: {tables_df}")

                    if not tables_df.empty and len(tables_df) > 0:
                        # Try different possible column names for table listing
                        possible_columns = [
                            f'Tables_in_{connector_name}',
                            'table_name',
                            'name',
                            'TABLE_NAME'
                        ]

                        for col in possible_columns:
                            if col in tables_df.columns:
                                table_name = tables_df.iloc[0][col]
                                logger.info(f"🎯 Found table: {table_name} using column: {col}")
                                break
                        else:
                            # If no specific column found, try to get the first column value
                            if len(tables_df.columns) > 0:
                                table_name = tables_df.iloc[0, 0]
                                logger.info(f"🎯 Using first column value as table name: {table_name}")
                    else:
                        logger.warning(f"⚠️ SHOW TABLES returned empty result, using default 'data'")

            except Exception as e:
                logger.warning(f"⚠️ Could not list tables: {e}, using default 'data'")
                table_name = "data"

            # Test the connector with multiple approaches
            result = None

            # Approach 1: Try with database context switching
            try:
                logger.info(f"🔄 Switching to database: {connector_name}")
                self.connection.query(f"USE {connector_name}")

                simple_test_query = f"SELECT * FROM {table_name} LIMIT 3"
                logger.info(f"🧪 Testing with context switch: {simple_test_query}")
                result = self.connection.query(simple_test_query)

                # Switch back to mindsdb database
                self.connection.query("USE mindsdb")
                logger.info(f"✅ Context switch approach successful")

            except Exception as context_error:
                logger.warning(f"⚠️ Context switch approach failed: {context_error}")

                # Approach 2: Try with fully qualified table name
                try:
                    # Ensure we're back in mindsdb context
                    self.connection.query("USE mindsdb")

                    full_test_query = f"SELECT * FROM {connector_name}.{table_name} LIMIT 3"
                    logger.info(f"🧪 Testing with fully qualified name: {full_test_query}")
                    result = self.connection.query(full_test_query)
                    logger.info(f"✅ Fully qualified approach successful")

                except Exception as qualified_error:
                    logger.warning(f"⚠️ Fully qualified approach failed: {qualified_error}")

                    # Approach 3: Try different common table names
                    common_table_names = ["data", "table", "result", "response", "json"]
                    for test_table_name in common_table_names:
                        try:
                            alternate_query = f"SELECT * FROM {connector_name}.{test_table_name} LIMIT 3"
                            logger.info(f"🧪 Testing alternate table name: {alternate_query}")
                            result = self.connection.query(alternate_query)
                            logger.info(f"✅ Found working table name: {test_table_name}")
                            table_name = test_table_name  # Update the working table name
                            break
                        except Exception as alt_error:
                            logger.debug(f"❌ Table '{test_table_name}' not found: {alt_error}")
                            continue

            if result and hasattr(result, 'fetch'):
                df = result.fetch()
                if not df.empty:
                    logger.info(f"✅ Web connector test successful - retrieved {len(df)} rows")
                    return {
                        "success": True,
                        "rows_retrieved": len(df),
                        "columns": list(df.columns),
                        "sample_data": _records_from_df(df.head(3)),
                        "table_name": table_name
                    }
                else:
                    logger.warning(f"⚠️ Web connector test returned no data")
                    return {
                        "success": False,
                        "error": "No data returned from web connector",
                        "table_name": table_name
                    }
            else:
                logger.warning(f"⚠️ Web connector test failed - no result")
                return {
                    "success": False,
                    "error": "Query execution failed"
                }

        except Exception as e:
            logger.error(f"❌ Web connector test failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def create_dataset_from_web_connector(
        self,
        connector_name: str,
        dataset_name: str,
        table_name: str = "data"
    ) -> Dict[str, Any]:
        """Create a dataset view from a web connector."""
        try:
            if not self.ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Clean names for MindsDB
            clean_connector = connector_name.lower().replace(' ', '_').replace('-', '_')
            clean_dataset = dataset_name.lower().replace(' ', '_').replace('-', '_')

            # Create a view that can be used for ML models
            # Ensure we're in the mindsdb database context for view creation
            create_view_sql = f"""
            CREATE OR REPLACE VIEW {clean_dataset}_view AS
            SELECT * FROM {clean_connector}.{table_name};
            """

            logger.info(f"📊 Creating dataset view: {clean_dataset}_view")
            logger.info(f"📄 SQL: {create_view_sql}")

            # Ensure we're in the mindsdb database for view creation
            try:
                self.connection.query("USE mindsdb")
                result = self.connection.query(create_view_sql)
            except Exception as view_error:
                logger.error(f"❌ View creation failed: {view_error}")
                raise view_error

            # Test the view
            test_query = f"SELECT * FROM {clean_dataset}_view LIMIT 5"
            test_result = self.connection.query(test_query)

            sample_data = []
            columns = []
            row_count = 0

            if test_result and hasattr(test_result, 'fetch'):
                df = test_result.fetch()
                if not df.empty:
                    sample_data = _records_from_df(df.head(5))
                    columns = list(df.columns)

                    # Try to get total row count
                    try:
                        count_query = f"SELECT COUNT(*) as total_rows FROM {clean_dataset}_view"
                        count_result = self.connection.query(count_query)
                        count_df = count_result.fetch()
                        if not count_df.empty:
                            row_count = count_df.iloc[0]['total_rows']
                    except:
                        row_count = len(df)

            logger.info(f"✅ Dataset view {clean_dataset}_view created successfully")

            return {
                "success": True,
                "view_name": f"{clean_dataset}_view",
                "connector_name": clean_connector,
                "columns": columns,
                "sample_data": sample_data,
                "estimated_rows": row_count,
                "message": f"Dataset view {clean_dataset}_view created from web connector"
            }

        except Exception as e:
            logger.error(f"❌ Failed to create dataset from web connector: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ------------------------------------------------------------------
    # File database connectors
    # ------------------------------------------------------------------

    def create_file_database_connector(self, file_upload: "FileUpload") -> Dict[str, Any]:
        """Create MindsDB database connector for uploaded files to make them accessible."""
        try:
            if not self.ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Generate file name for MindsDB upload
            mindsdb_file_name = f"dataset_{file_upload.dataset_id}_file_{file_upload.id}"

            # Determine the appropriate engine and parameters based on file type
            file_ext = os.path.splitext(file_upload.original_filename.lower())[1].lstrip('.')

            # Download file from S3 and upload to MindsDB
            logger.info(f"📤 Downloading file from S3 and uploading to MindsDB: {file_upload.original_filename}")

            temp_file_path = None
            uploaded_file_name = None

            try:
                # Download file from S3 using boto3
                import boto3
                import tempfile

                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'),
                    endpoint_url=os.getenv('S3_ENDPOINT_URL'),
                    region_name=os.getenv('S3_REGION', 'us-east-1')
                )

                # Create temp file
                temp_dir = tempfile.gettempdir()
                temp_file_path = os.path.join(temp_dir, f"mindsdb_upload_{file_upload.id}_{file_upload.original_filename}")

                # Download from S3
                logger.info(f"⬇️  Downloading from S3: {file_upload.file_path}")
                s3_client.download_file(
                    os.getenv('S3_BUCKET_NAME'),
                    file_upload.file_path,
                    temp_file_path
                )
                logger.info(f"✅ Downloaded to temp: {temp_file_path}")

                # Upload to MindsDB
                uploaded_file_name = self.upload_file_to_mindsdb(temp_file_path, mindsdb_file_name)

                if not uploaded_file_name:
                    raise Exception("Failed to upload file to MindsDB")

                logger.info(f"✅ File uploaded to MindsDB as: {uploaded_file_name}")

            except Exception as download_error:
                logger.error(f"❌ Failed to download/upload file: {download_error}")
                raise Exception(f"Failed to prepare file for MindsDB: {download_error}")
            finally:
                # Clean up temp file
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        logger.debug(f"🧹 Cleaned up temp file: {temp_file_path}")
                    except:
                        pass

            # Files uploaded to MindsDB are accessible via the "files" database directly
            # No need to create a separate database connector
            # The uploaded file is accessible at: files.{uploaded_file_name}

            logger.info(f"✅ File uploaded to MindsDB: files.{uploaded_file_name}")

            # Test the connector by trying to fetch data from the files database
            test_result = self.test_file_database_connector("files", file_upload, uploaded_file_name)

            return {
                "success": True,
                "database_name": "files",  # Use the built-in files database
                "engine": "files",
                "file_path": file_upload.file_path,
                "file_type": file_ext,
                "uploaded_filename": uploaded_file_name,  # Return the uploaded filename
                "test_result": test_result,
                "message": f"File uploaded to MindsDB files database as {uploaded_file_name}"
            }

        except Exception as e:
            logger.error(f"❌ Failed to create file database connector for {file_upload.original_filename}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_upload_id": file_upload.id
            }

    def test_file_database_connector(self, database_name: str, file_upload: "FileUpload", uploaded_file_name: str = None) -> Dict[str, Any]:
        """Test a file database connector by fetching sample data."""
        try:
            if not self.ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Try different table names that MindsDB might use for file data
            possible_table_names = []

            # If we have the uploaded file name, try it first
            if uploaded_file_name:
                possible_table_names.append(uploaded_file_name)

            # Then try other common patterns
            possible_table_names.extend([
                file_upload.original_filename.split('.')[0],  # filename without extension
                "data",  # common default
                "file",  # another common default
                f"uploaded_file_{file_upload.id}"  # our custom name
            ])

            for table_name in possible_table_names:
                try:
                    # Clean table name for SQL
                    clean_table = table_name.lower().replace(' ', '_').replace('-', '_')
                    test_query = f"SELECT * FROM {database_name}.{clean_table} LIMIT 3"

                    logger.info(f"🧪 Testing file database connector: {test_query}")

                    result = self.connection.query(test_query)

                    if result and hasattr(result, 'fetch'):
                        df = result.fetch()
                        if not df.empty:
                            logger.info(f"✅ File database test successful with table '{clean_table}' - retrieved {len(df)} rows")
                            return {
                                "success": True,
                                "table_name": clean_table,
                                "rows_retrieved": len(df),
                                "columns": list(df.columns),
                                "sample_data": _records_from_df(df.head(3))
                            }
                except Exception as table_error:
                    logger.debug(f"Table '{clean_table}' not found: {table_error}")
                    continue

            # If no table worked, return partial success (database exists but no accessible tables)
            logger.warning(f"⚠️ File database connector created but no accessible tables found")
            return {
                "success": True,
                "warning": "Database created but no accessible tables found",
                "tried_tables": possible_table_names
            }

        except Exception as e:
            logger.error(f"❌ File database connector test failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # ------------------------------------------------------------------
    # Chat (legacy wrapper)
    # ------------------------------------------------------------------

    async def chat_with_dataset(self, dataset_id: str, message: str, user_id: Optional[int] = None, session_id: Optional[str] = None, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Legacy chat method - now just a wrapper around chat_with_dataset_agent().
        This maintains backward compatibility while using the agent-based architecture.
        """
        try:
            logger.info(f"🔄 chat_with_dataset() wrapping to chat_with_dataset_agent() for dataset {dataset_id}")

            # Get database session
            from app.core.database import get_db
            db = next(get_db())

            # Call the agent-based chat method
            result = await self.chat_with_dataset_agent(
                dataset_id=int(dataset_id),
                message=message,
                db=db,
                session_id=session_id,
                stream=True
            )

            return result
        except Exception as e:
            logger.error(f"❌ Dataset chat failed: {e}")
            return {
                "error": f"Dataset chat failed: {str(e)}",
                "answer": "I'm sorry, but I encountered an error while processing your question.",
                "dataset_id": dataset_id,
                "timestamp": datetime.utcnow().isoformat()
            }

    # ------------------------------------------------------------------
    # File type helpers
    # ------------------------------------------------------------------

    def is_supported_file_type(self, file_path: str) -> bool:
        """Check if file type is supported by MindsDB."""
        ext = os.path.splitext(file_path.lower())[1]
        return ext in self.SUPPORTED_FILE_EXTENSIONS

    def get_file_type(self, file_path: str) -> Optional[str]:
        """Get MindsDB file type from file path."""
        ext = os.path.splitext(file_path.lower())[1]
        return self.SUPPORTED_FILE_EXTENSIONS.get(ext)

    def upload_file_to_mindsdb(self, full_path: str, file_name: str) -> Optional[str]:
        """Upload file to MindsDB files database."""

        if not os.path.exists(full_path):
            logger.error(f"File not found at: {full_path}")
            return None

        if not self.is_supported_file_type(full_path):
            ext = os.path.splitext(full_path.lower())[1]
            logger.error(f"Unsupported file type: {ext}")
            return None

        logger.info(f"✅ Found supported file: {full_path}")

        try:
            # Determine MIME type based on extension
            mime_types = {
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.json': 'application/json',
                '.txt': 'text/plain',
                '.pdf': 'application/pdf',
                '.parquet': 'application/octet-stream'
            }

            ext = os.path.splitext(full_path.lower())[1]
            mime_type = mime_types.get(ext, 'application/octet-stream')

            # Upload file to MindsDB
            with open(full_path, 'rb') as f:
                files = {'file': (file_name + ext, f, mime_type)}
                response = requests.put(
                    f"{self.base_url}/api/files/{file_name}",
                    files=files
                )

            if response.status_code == 200:
                logger.info(f"✅ Successfully uploaded {ext} file to MindsDB as '{file_name}'")
                return file_name
            elif response.status_code == 400 and "already exists" in response.text.lower():
                # File already exists in MindsDB - this is OK, we can use the existing file
                logger.info(f"♻️  File already exists in MindsDB: {file_name}, using existing file")
                return file_name
            else:
                logger.error(f"❌ Failed to upload file to MindsDB: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ Error uploading to MindsDB: {e}")
            return None

    def delete_file_from_mindsdb(self, file_name: str) -> bool:
        """Delete file from MindsDB files database."""
        try:
            logger.info(f"🗑️  Deleting file from MindsDB: {file_name}")

            # Delete file using MindsDB API
            response = requests.delete(
                f"{self.base_url}/api/files/{file_name}"
            )

            if response.status_code in [200, 204]:
                logger.info(f"✅ Successfully deleted file from MindsDB: {file_name}")
                return True
            elif response.status_code == 404:
                logger.warning(f"⚠️  File not found in MindsDB: {file_name}")
                return True  # Consider success if file doesn't exist
            else:
                logger.error(f"❌ Failed to delete file from MindsDB: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Error deleting file from MindsDB: {e}")
            return False

    def delete_database_connector(self, database_name: str) -> bool:
        """Delete database connector from MindsDB."""
        try:
            if not self.ensure_connection():
                return False

            logger.info(f"🗑️  Deleting database connector: {database_name}")

            # Drop database using MindsDB SQL
            drop_db_sql = f"DROP DATABASE IF EXISTS {database_name};"
            self.connection.query(drop_db_sql)

            logger.info(f"✅ Successfully deleted database connector: {database_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Error deleting database connector {database_name}: {e}")
            return False

    def setup_file_dataset_processing(self, dataset, db_session) -> Dict[str, Any]:
        """Setup MindsDB processing for uploaded file dataset."""
        try:
            if not dataset.file_path:
                return {"success": False, "error": "No file path in dataset"}

            if not self.is_supported_file_type(dataset.file_path):
                file_ext = os.path.splitext(dataset.file_path.lower())[1]
                return {"success": False, "error": f"Unsupported file type: {file_ext}"}

            # Get storage path
            from app.services.storage import StorageService
            storage_service = StorageService()
            if hasattr(storage_service, 'backend') and hasattr(storage_service.backend, 'storage_dir'):
                storage_base = storage_service.backend.storage_dir
            else:
                from app.core.config import settings
                storage_base = os.path.abspath(settings.DATASET_STORAGE_PATH)

            full_path = os.path.join(storage_base, dataset.file_path)
            file_type = self.get_file_type(dataset.file_path)
            file_name = f"dataset_{dataset.id}_{file_type}"

            logger.info(f"📁 Processing {file_type.upper()} file for dataset {dataset.id}")

            # Upload to MindsDB
            uploaded_name = self.upload_file_to_mindsdb(full_path, file_name)
            if not uploaded_name:
                return {"success": False, "error": "Failed to upload file to MindsDB"}

            # File is now available in MindsDB as files.<uploaded_name>.
            # Model training is user-initiated via POST /api/models — no
            # automatic model creation here.
            dataset.mindsdb_table_name = uploaded_name
            dataset.mindsdb_database = "files"
            dataset.ai_processing_status = "ready"

            # Update chat context
            if hasattr(dataset, 'chat_context') and dataset.chat_context:
                dataset.chat_context['mindsdb_datasource'] = uploaded_name
                dataset.chat_context['mindsdb_available'] = True
                dataset.chat_context['model_name'] = uploaded_name
                dataset.chat_context['file_type'] = file_type

            db_session.commit()

            logger.info(f"✅ Completed MindsDB setup for dataset {dataset.id}")

            return {
                "success": True,
                "model_name": model_name,
                "uploaded_name": uploaded_name,
                "file_type": file_type
            }

        except Exception as e:
            logger.error(f"❌ Error setting up file dataset processing: {e}")
            db_session.rollback()
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Identifier safety
    # ------------------------------------------------------------------

    def is_safe_mindsdb_identifier(self, identifier: Optional[str]) -> bool:
        """Check whether *identifier* is safe for use in SQL identifiers.

        Allows only ``[A-Za-z_][A-Za-z0-9_]*`` — rejects empty, ``None``,
        and any string that could enable SQL injection.
        """
        if not identifier:
            return False
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier))

    def _is_safe_mindsdb_identifier(self, identifier: Optional[str]) -> bool:
        """Deprecated: use is_safe_mindsdb_identifier() instead."""
        return self.is_safe_mindsdb_identifier(identifier)

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def load_mindsdb_table_for_visualization(self, dataset, limit: int = 10000) -> Optional[pd.DataFrame]:
        """Load a MindsDB connector-backed table into a DataFrame for visualization."""
        database_name = getattr(dataset, "mindsdb_database", None)
        table_name = getattr(dataset, "mindsdb_table_name", None)
        if not database_name or not table_name:
            return None

        if not self.is_safe_mindsdb_identifier(database_name) or not self.is_safe_mindsdb_identifier(table_name):
            logger.warning(f"Unsafe MindsDB identifier for dataset {dataset.id}: {database_name}.{table_name}")
            return None

        if not self.ensure_connection():
            logger.warning(f"MindsDB connection unavailable for dataset {dataset.id} visualization")
            return None

        query = f"SELECT * FROM {database_name}.{table_name} LIMIT {max(1, min(limit, 10000))}"
        logger.info(f"📊 Loading connector-backed dataset for visualization: {database_name}.{table_name}")
        result = self.connection.query(query)
        if not result or not hasattr(result, "fetch"):
            logger.warning(f"MindsDB query returned no fetchable result for dataset {dataset.id}")
            return None

        df = result.fetch()
        if df is None or not hasattr(df, "empty"):
            logger.warning(f"MindsDB query returned non-DataFrame result for dataset {dataset.id}")
            return None
        if len(df) > limit:
            df = df.head(limit)
        return df

    def _load_mindsdb_table_for_visualization(self, dataset, limit: int = 10000) -> Optional[pd.DataFrame]:
        """Deprecated: use load_mindsdb_table_for_visualization() instead."""
        return self.load_mindsdb_table_for_visualization(dataset, limit)

    async def load_dataset_for_visualization(self, dataset, db) -> Optional[pd.DataFrame]:
        """Load dataset data into a DataFrame for visualization (async).

        Tries MindsDB connector first; falls back to reading the file from
        storage (S3 or local).
        """
        try:
            connector_df = self.load_mindsdb_table_for_visualization(dataset)
            if connector_df is not None:
                return connector_df

            # Check if dataset has files
            file_path = None
            if dataset.is_multi_file_dataset:
                # For multi-file datasets, load the primary file
                from app.models.dataset import DatasetFile
                dataset_files = db.query(DatasetFile).filter(
                    DatasetFile.dataset_id == dataset.id,
                    DatasetFile.is_deleted == False
                ).order_by(DatasetFile.is_primary.desc()).all()

                if dataset_files:
                    primary_file = dataset_files[0]
                    file_path = primary_file.file_path
                else:
                    logger.warning(f"No files found for multi-file dataset {dataset.id}")
                    return None
            else:
                # For single file datasets
                file_path = dataset.file_path
                if not file_path and dataset.source_url and not dataset.source_url.startswith('http'):
                    file_path = dataset.source_url

            if not file_path:
                logger.warning(f"No file path found for dataset {dataset.id}")
                return None

            # Determine file extension
            file_extension = file_path.split('.')[-1].lower()

            # Try to load file - check if it's a local path or S3 path
            file_content = None

            # If path looks like S3 (org_1/dataset_X...), use async S3 client
            if file_path.startswith('org_') or not os.path.exists(file_path):
                logger.info(f"📥 Downloading file from S3 storage: {file_path}")
                try:
                    # Try importing aioboto3
                    try:
                        import aioboto3
                        from botocore.exceptions import ClientError
                    except ImportError as import_error:
                        logger.error(f"❌ aioboto3 not available: {import_error}")
                        logger.error("Please install aioboto3: pip install aioboto3")
                        return None

                    # Create async session
                    session = aioboto3.Session()

                    bucket_name = os.getenv('S3_BUCKET_NAME')

                    # Use async context manager for S3 client
                    async with session.client(
                        's3',
                        endpoint_url=os.getenv('S3_ENDPOINT_URL'),
                        aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
                        aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY'),
                        region_name=os.getenv('S3_REGION', 'us-east-1')
                    ) as s3_client:
                        # Download file content asynchronously
                        logger.info(f"Downloading from bucket {bucket_name}: {file_path}")
                        response = await s3_client.get_object(Bucket=bucket_name, Key=file_path)

                        # Read body asynchronously
                        async with response['Body'] as stream:
                            file_content = await stream.read()

                        if not file_content:
                            logger.warning(f"Could not retrieve file from S3: {file_path}")
                            return None

                        logger.info(f"✅ Retrieved {len(file_content)} bytes from S3")

                except ClientError as s3_error:
                    logger.error(f"S3 client error: {s3_error}")
                    return None
                except Exception as storage_error:
                    logger.error(f"Failed to get file from storage: {storage_error}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return None
            else:
                # Local file - read directly (use aiofiles for async)
                logger.info(f"📁 Reading local file: {file_path}")
                try:
                    import aiofiles
                    async with aiofiles.open(file_path, 'rb') as f:
                        file_content = await f.read()
                except Exception as read_error:
                    logger.error(f"Failed to read local file: {read_error}")
                    return None

            # Load file based on type using BytesIO
            df = None
            try:
                if file_extension == 'csv':
                    df = pd.read_csv(io.BytesIO(file_content))
                elif file_extension in ['xlsx', 'xls']:
                    df = pd.read_excel(io.BytesIO(file_content))
                elif file_extension == 'json':
                    df = pd.read_json(io.BytesIO(file_content))
                elif file_extension == 'parquet':
                    df = pd.read_parquet(io.BytesIO(file_content))
                else:
                    logger.warning(f"Unsupported file type for visualization: {file_extension}")
                    return None

                logger.info(f"✅ Loaded DataFrame with {len(df)} rows, {len(df.columns)} columns")

            except Exception as parse_error:
                logger.error(f"Failed to parse file as {file_extension}: {parse_error}")
                return None

            # Limit rows for performance
            if len(df) > 10000:
                logger.info(f"Dataset has {len(df)} rows, sampling 10000 for visualization")
                df = df.sample(n=10000, random_state=42)

            return df

        except Exception as e:
            logger.error(f"Error loading dataset for visualization: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def _load_dataset_for_visualization(self, dataset, db) -> Optional[pd.DataFrame]:
        """Deprecated: use load_dataset_for_visualization() instead."""
        return await self.load_dataset_for_visualization(dataset, db)

    def process_file_content(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """Extract content and metadata from a file (pdf/json) for preview purposes.

        Returns a dict with keys ``success``, ``content`` (string preview),
        and ``metadata`` (dict with ``element_count`` etc.).
        """
        result: Dict[str, Any] = {"success": False, "content": "", "metadata": {}}
        try:
            if file_type == "pdf":
                processor = PDFProcessingService()
                pdf_result = processor.process_pdf(file_path)
                if pdf_result.get("success"):
                    result["success"] = True
                    result["content"] = pdf_result.get("text_content", "")
                    result["metadata"] = pdf_result.get("metadata", {})
                return result

            if file_type == "json":
                import json as json_module
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json_module.load(f)
                content_str = json_module.dumps(data, indent=2)[:2000]
                result["success"] = True
                result["content"] = content_str
                result["metadata"] = {"element_count": _count_json_elements(data)}
                return result

            logger.warning(f"Unsupported file type for content extraction: {file_type}")
            return result

        except Exception as e:
            logger.error(f"Failed to process file content: {e}")
            result["error"] = str(e)
            return result

    # ============================================================
    # MODEL TRAINING — CREATE MODEL / predict / status / delete
    # ============================================================
    #
    # These methods generate MindsDB SQL and execute it through
    # self.execute_query() so that all connection and error handling
    # is reused.  Identifiers are validated via
    # is_safe_mindsdb_identifier() — unsafe ones raise ValueError.
    #
    # The method names match the call sites in app/api/mindsdb.py,
    # making those routes functional as a side effect.

    def get_models(self) -> List[Dict[str, Any]]:
        """List all models from MindsDB via SELECT * FROM mindsdb.models."""
        result = self.execute_query("SELECT * FROM mindsdb.models")
        if result.get("status") == "error":
            logger.warning(f"Failed to fetch models: {result.get('error')}")
            return []
        return result.get("rows", [])

    def create_model(
        self,
        model_name: str,
        query: str,
        engine: str = "mindsdb",
        predict: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a model via async CREATE MODEL SQL.

        Returns the raw execute_query result dict (status, rows, etc.).
        The model starts in 'training' status — call get_model_info()
        to poll for completion.
        """
        # Validate identifiers
        if not self.is_safe_mindsdb_identifier(model_name):
            raise ValueError(f"Unsafe model name: {model_name}")
        if predict is not None and not self.is_safe_mindsdb_identifier(predict):
            raise ValueError(f"Unsafe predict column: {predict}")

        sql = f"CREATE MODEL mindsdb.{model_name}\n"
        sql += f"FROM {engine} ({query})\n"
        if predict:
            sql += f"PREDICT `{predict}`\n"
        if options:
            opts = ", ".join(f"{k} = {v}" for k, v in options.items())
            sql += f"WITH ({opts})\n"

        logger.info(f"🔍 Creating model: {model_name}")
        return self.execute_query(sql.strip())

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get a single model's info by name, or None if not found.

        Runs SELECT * FROM mindsdb.models WHERE name = '<model_name>'.
        """
        if not self.is_safe_mindsdb_identifier(model_name):
            raise ValueError(f"Unsafe model name: {model_name}")

        sql = f"SELECT * FROM mindsdb.models WHERE name = '{model_name}'"
        result = self.execute_query(sql)
        rows = result.get("rows", [])
        return rows[0] if rows else None

    def predict(
        self, model_name: str, prediction_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run a prediction using the named model.

        *prediction_data* maps column names to values; each becomes a
        WHERE clause term (AND-joined).  Returns a list of result-row
        dicts.
        """
        if not self.is_safe_mindsdb_identifier(model_name):
            raise ValueError(f"Unsafe model name: {model_name}")

        clauses = [
            f"{col} = {self._format_sql_literal(val)}"
            for col, val in prediction_data.items()
        ]
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM mindsdb.{model_name} WHERE {where}"
        result = self.execute_query(sql)
        return result.get("rows", [])

    def delete_model(self, model_name: str) -> bool:
        """DROP MODEL IF EXISTS — returns True on success."""
        if not self.is_safe_mindsdb_identifier(model_name):
            raise ValueError(f"Unsafe model name: {model_name}")

        sql = f"DROP MODEL IF EXISTS mindsdb.{model_name}"
        result = self.execute_query(sql)
        return result.get("status") == "success"

    @staticmethod
    def _format_sql_literal(value: Any) -> str:
        """Format a Python value as a SQL literal.

        Handles None → NULL, bool → True/False, int/float → str,
        str → single-quoted with '' escaping.
        """
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (int, float)):
            return str(value)
        # string: escape single quotes by doubling them
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    # ============================================================
    # AGENT-BASED ARCHITECTURE METHODS — delegated to sub-services
    # ============================================================

    # -- Agent CRUD (delegated to DatasetConnectorService) --

    def _create_agent_with_default_llm(self, agent_name: str, tables: List[str], prompt_template: str):
        return self._connector_service._create_agent_with_default_llm(agent_name, tables, prompt_template)

    def create_or_get_agent(self, agent_name: str, tables: List[str], prompt_template: str,
                            model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._connector_service.create_or_get_agent(agent_name, tables, prompt_template, model_config)

    def update_agent(self, agent_name: str, new_tables: List[str] = None,
                     new_prompt: str = None, new_model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._connector_service.update_agent(agent_name, new_tables, new_prompt, new_model_config)

    def delete_agent(self, agent_name: str) -> bool:
        return self._connector_service.delete_agent(agent_name)

    def clear_dataset_agent_metadata(self, dataset, db) -> None:
        self._connector_service.clear_dataset_agent_metadata(dataset, db)

    def delete_dataset_agent(self, dataset, db) -> bool:
        return self._connector_service.delete_dataset_agent(dataset, db)

    def list_agents(self) -> List[str]:
        return self._connector_service.list_agents()

    # -- Agent setup (delegated to DatasetConnectorService) --

    def setup_single_file_agent(self, dataset, db) -> Dict[str, Any]:
        return self._connector_service.setup_single_file_agent(dataset, db)

    def setup_multi_file_agent(self, dataset, db) -> Dict[str, Any]:
        return self._connector_service.setup_multi_file_agent(dataset, db)

    # -- Prompt templates (delegated to prompt_templates module) --

    def _build_single_file_prompt(self, dataset, file_upload, database_name: str, table_name: str) -> str:
        return build_single_file_prompt(dataset, file_upload, database_name, table_name)

    def _build_multi_file_prompt(self, dataset, dataset_files, file_descriptions: List[str],
                                 all_tables: List[str]) -> str:
        return build_multi_file_prompt(dataset, dataset_files, file_descriptions, all_tables)

    # -- Chat agent (delegated to ChatAgentService) --

    async def chat_with_dataset_agent(self, dataset_id: int, message: str, db,
                                      session_id: str = None, stream: bool = True) -> Dict[str, Any]:
        return await self._chat_agent_service.chat_with_dataset_agent(
            dataset_id, message, db, session_id, stream
        )

    async def _chat_with_dataset_summary_fallback(
        self, dataset, message: str, db, start_time: float,
        visualizations: Optional[List[Dict[str, Any]]] = None,
        data_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self._chat_agent_service._chat_with_dataset_summary_fallback(
            dataset, message, db, start_time, visualizations, data_analysis
        )

    def _clean_agent_answer(self, answer: str) -> str:
        return clean_agent_answer(answer)

    def _build_dataset_summary_answer(self, dataset, message: str, dataset_df: pd.DataFrame,
                                       data_analysis: Dict[str, Any]) -> str:
        return build_dataset_summary_answer(dataset, message, dataset_df, data_analysis)


# Global service instance
mindsdb_service = MindsDBService()
