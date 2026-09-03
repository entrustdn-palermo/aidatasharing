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
import time
import requests
import pandas as pd
import io
import re

# Import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.file_handler import FileUpload

logger = logging.getLogger(__name__)


def _records_from_df(df: pd.DataFrame) -> list:
    """Convert a DataFrame to a list of dicts with numpy types handled."""
    if df is None or df.empty:
        return []
    import numpy as np
    records = _records_from_df(df)
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

        logger.info("✅ MindsDB Service initialized in agent-based mode")

    def _ensure_connection(self) -> bool:
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

    def health_check(self) -> Dict[str, Any]:
        """Perform health check of MindsDB service."""
        try:
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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




    def create_dataset_connection(self, dataset_name: str, file_url: str, file_type: str = "csv") -> Dict[str, Any]:
        """Create a dataset connection in MindsDB using a file URL."""
        try:
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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

    def create_file_database_connector(self, file_upload: "FileUpload") -> Dict[str, Any]:
        """Create MindsDB database connector for uploaded files to make them accessible."""
        try:
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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
            if not self._ensure_connection():
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
                storage_base = os.path.abspath(settings.STORAGE_BASE_PATH)
            
            full_path = os.path.join(storage_base, dataset.file_path)
            file_type = self.get_file_type(dataset.file_path)
            file_name = f"dataset_{dataset.id}_{file_type}"
            
            logger.info(f"📁 Processing {file_type.upper()} file for dataset {dataset.id}")
            
            # Upload to MindsDB
            uploaded_name = self.upload_file_to_mindsdb(full_path, file_name)
            if not uploaded_name:
                return {"success": False, "error": "Failed to upload file to MindsDB"}
            
            # Create model
            model_name = self.create_model_for_uploaded_file(uploaded_name, file_type)
            if not model_name:
                return {"success": False, "error": "Failed to create MindsDB model"}
            
            # Update dataset
            dataset.mindsdb_table_name = model_name
            dataset.mindsdb_database = "mindsdb"
            dataset.ai_processing_status = "ready"
            
            # Update chat context
            if hasattr(dataset, 'chat_context') and dataset.chat_context:
                dataset.chat_context['mindsdb_datasource'] = uploaded_name
                dataset.chat_context['mindsdb_available'] = True
                dataset.chat_context['model_name'] = model_name
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
    
    def _is_safe_mindsdb_identifier(self, identifier: Optional[str]) -> bool:
        if not identifier:
            return False
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier))

    def _load_mindsdb_table_for_visualization(self, dataset, limit: int = 10000) -> Optional[pd.DataFrame]:
        database_name = getattr(dataset, "mindsdb_database", None)
        table_name = getattr(dataset, "mindsdb_table_name", None)
        if not database_name or not table_name:
            return None

        if not self._is_safe_mindsdb_identifier(database_name) or not self._is_safe_mindsdb_identifier(table_name):
            logger.warning(f"Unsafe MindsDB identifier for dataset {dataset.id}: {database_name}.{table_name}")
            return None

        if not self._ensure_connection():
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

    async def _load_dataset_for_visualization(self, dataset, db) -> Optional[pd.DataFrame]:
        """Load dataset data into a DataFrame for visualization (async)"""
        try:
            connector_df = self._load_mindsdb_table_for_visualization(dataset)
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

    # ============================================================
    # AGENT-BASED ARCHITECTURE METHODS (New)
    # ============================================================


    def _create_agent_with_default_llm(self, agent_name: str, tables: List[str], prompt_template: str):
        payload = {
            "agent": {
                "name": agent_name,
                "data": {"tables": tables},
                "prompt_template": prompt_template,
                "params": {}
            }
        }
        response = requests.post(
            f"{self.base_url}/api/projects/mindsdb/agents",
            json=payload,
            timeout=120
        )
        if response.status_code == 409:
            return self.connection.agents.get(agent_name)
        response.raise_for_status()
        return self.connection.agents.get(agent_name)

    def create_or_get_agent(self, agent_name: str, tables: List[str], prompt_template: str,
                           model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create or retrieve an agent for a specific dataset.
        Agents are persistent and reusable across chat sessions.

        Args:
            agent_name: Unique name for the agent
            tables: List of table references (e.g., ['file_db_1.data', 'file_db_2.data'])
            prompt_template: System prompt for the agent
            model_config: Optional model configuration (provider, model_name, api_key)

        Returns:
            Dict with success status, agent reference, and agent_name
        """
        if not self._ensure_connection():
            return {
                "success": False,
                "error": "Failed to connect to MindsDB"
            }

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
            except Exception as e:
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
            return {
                "success": False,
                "error": str(e)
            }

    def update_agent(self, agent_name: str, new_tables: List[str] = None,
                    new_prompt: str = None, new_model_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Update agent's data sources, prompt, or model configuration.
        Used when dataset changes (files added/removed).

        Args:
            agent_name: Name of the agent to update
            new_tables: Optional new list of tables
            new_prompt: Optional new prompt template
            new_model_config: Optional new model configuration

        Returns:
            Dict with success status and message
        """
        try:
            # For now, we'll delete and recreate the agent
            # MindsDB SDK may not support direct agent updates yet
            self.delete_agent(agent_name)
            logger.info(f"🔄 Agent {agent_name} deleted for recreation")

            return {
                "success": True,
                "message": f"Agent {agent_name} marked for recreation",
                "action": "recreate"
            }

        except Exception as e:
            logger.error(f"❌ Failed to update agent {agent_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_agent(self, agent_name: str) -> bool:
        """
        Delete agent when dataset is deleted or needs recreation.

        Args:
            agent_name: Name of the agent to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete via REST API (SDK may not have delete method)
            response = requests.delete(
                f"{self.base_url}/api/projects/mindsdb/agents/{agent_name}"
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
        """
        List all available agents in MindsDB.
        Useful for debugging and monitoring.

        Returns:
            List of agent names
        """
        if not self._ensure_connection():
            return []

        try:
            # Try to list agents via SDK
            agents = self.connection.agents.list()
            agent_names = [agent.name for agent in agents]
            logger.info(f"📋 Found {len(agent_names)} agents")
            return agent_names
        except Exception as e:
            logger.error(f"❌ Failed to list agents: {e}")
            return []

    def setup_single_file_agent(self, dataset, db) -> Dict[str, Any]:
        """
        Create an agent for a single-file dataset.
        This replaces the old model-based approach with persistent agents.

        Args:
            dataset: Dataset model instance
            db: Database session

        Returns:
            Dict with success status, agent_name, and table info
        """
        try:
            logger.info(f"🔧 Setting up single-file agent for dataset: {dataset.name} (ID: {dataset.id})")

            # Generate agent name
            agent_name = f"dataset_{dataset.id}_agent"

            # Check if agent already exists and is current
            if dataset.agent_name == agent_name and dataset.agent_created_at:
                logger.info(f"♻️  Agent already exists: {agent_name}")
                # Verify it exists in MindsDB
                try:
                    agent = self.connection.agents.get(agent_name)
                    return {
                        "success": True,
                        "agent_name": agent_name,
                        "status": "existing",
                        "agent": agent
                    }
                except:
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
                # Use existing FileUpload record
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
                # Try to create connector directly from dataset file_path
                logger.info(f"📁 Creating connector from dataset file_path for dataset {dataset.id}")

                # Create a minimal FileUpload-like object for connector creation
                file_path = dataset.file_path or dataset.source_url

                # Only proceed if it's a data file (not image)
                if file_path and not any(file_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg']):
                    # Try to create connector using the setup_file_dataset_processing method
                    try:
                        from app.models.dataset import DatasetFile
                        dataset_files = db.query(DatasetFile).filter(
                            DatasetFile.dataset_id == dataset.id,
                            DatasetFile.is_deleted == False
                        ).all()

                        if dataset_files:
                            # Use the first file for single-file datasets
                            dataset_file = dataset_files[0]

                            # Generate database name
                            database_name = f"dataset_{dataset.id}_db"

                            # Create database in MindsDB
                            if self._ensure_connection():
                                try:
                                    # Create database if not exists
                                    self.connection.databases.create(
                                        name=database_name,
                                        engine='files'
                                    )
                                    logger.info(f"✅ Created MindsDB database: {database_name}")
                                    connector_result = {
                                        "success": True,
                                        "database_name": database_name,
                                        "test_result": {"table_name": table_name}
                                    }
                                except Exception as e:
                                    # Database might already exist
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
            prompt_template = self._build_single_file_prompt(dataset, file_upload, database_name, table_name)

            # Create or get agent (using MindsDB's pre-configured LLM)
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
            return {
                "success": False,
                "error": str(e)
            }

    def _build_single_file_prompt(self, dataset, file_upload, database_name: str, table_name: str) -> str:
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

    def setup_multi_file_agent(self, dataset, db) -> Dict[str, Any]:
        """
        Create an agent that can query ALL files in a multi-file dataset.
        This is the GAME CHANGER - enables cross-file analysis!

        Args:
            dataset: Dataset model instance (must be multi-file)
            db: Database session

        Returns:
            Dict with success status, agent_name, tables list, and file count
        """
        try:
            logger.info(f"🔧 Setting up MULTI-FILE agent for dataset: {dataset.name} (ID: {dataset.id})")

            if not dataset.is_multi_file_dataset:
                return {
                    "success": False,
                    "error": "Dataset is not a multi-file dataset"
                }

            # Generate agent name
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
                except:
                    logger.info(f"Agent {agent_name} not found in MindsDB, will recreate")

            # Get ALL files in the dataset
            from app.models.dataset import DatasetFile
            dataset_files = db.query(DatasetFile).filter(
                DatasetFile.dataset_id == dataset.id,
                DatasetFile.is_deleted == False
            ).all()

            if not dataset_files:
                return {
                    "success": False,
                    "error": "No files found in multi-file dataset"
                }

            logger.info(f"📁 Found {len(dataset_files)} files to include in agent")

            # Create database connector for EACH file and collect table references
            all_tables = []
            file_descriptions = []
            from app.models.file_handler import FileUpload

            for idx, dataset_file in enumerate(dataset_files, 1):
                logger.info(f"  Processing file {idx}/{len(dataset_files)}: {dataset_file.filename}")

                # Find corresponding file upload
                file_upload = db.query(FileUpload).filter(
                    FileUpload.dataset_id == dataset.id,
                    FileUpload.original_filename == dataset_file.filename
                ).first()

                if not file_upload:
                    logger.warning(f"  ⚠️  No upload record found for {dataset_file.filename}, skipping")
                    continue

                # Upload file to MindsDB and get the file reference
                connector_result = self.create_file_database_connector(file_upload)

                if connector_result.get("success"):
                    # Use direct file reference in MindsDB files database
                    # Format: files.{uploaded_filename}
                    uploaded_filename = connector_result.get("uploaded_filename")
                    if uploaded_filename:
                        full_table_ref = f"files.{uploaded_filename}"
                    else:
                        # Fallback to old connector format if upload didn't happen
                        database_name = connector_result["database_name"]
                        table_name = connector_result.get("test_result", {}).get("table_name", "data")
                        full_table_ref = f"{database_name}.{table_name}"

                    all_tables.append(full_table_ref)

                    # Create descriptive entry for prompt
                    file_type = dataset_file.file_type or "Unknown"
                    is_primary = "PRIMARY" if dataset_file.is_primary else "Supporting"
                    file_descriptions.append(
                        f"  - {full_table_ref}: {dataset_file.filename} ({file_type}, {is_primary})"
                    )

                    logger.info(f"    ✅ Added table: {full_table_ref}")
                else:
                    logger.warning(f"  ⚠️  Failed to create connector for {dataset_file.filename}")

            if not all_tables:
                return {
                    "success": False,
                    "error": "Failed to create database connectors for any files"
                }

            logger.info(f"📊 Agent will have access to {len(all_tables)} tables")

            # Build comprehensive multi-file prompt template
            prompt_template = self._build_multi_file_prompt(
                dataset, dataset_files, file_descriptions, all_tables
            )

            # Create or get agent with ALL tables (using MindsDB's pre-configured LLM)
            agent_result = self.create_or_get_agent(
                agent_name=agent_name,
                tables=all_tables,  # ← ALL FILES!
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
            return {
                "success": False,
                "error": str(e)
            }

    def _build_multi_file_prompt(self, dataset, dataset_files, file_descriptions: List[str],
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

    async def chat_with_dataset_agent(self, dataset_id: int, message: str, db,
                                session_id: str = None, stream: bool = True) -> Dict[str, Any]:
        """
        Chat with dataset using agent-based architecture.
        This is the main entry point replacing the old model-based chat.

        Features:
        - Persistent agents (no recreation overhead)
        - Multi-file support (cross-file analysis)
        - Streaming responses
        - Automatic fallback to direct API

        Args:
            dataset_id: Dataset ID
            message: User's question/message
            db: Database session
            session_id: Optional session ID for conversation history
            stream: Whether to stream response (default True)

        Returns:
            Dict with answer, metadata, and performance info
        """
        start_time = time.time()

        try:
            # Get dataset
            from app.models.dataset import Dataset
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

            if not dataset:
                return {
                    "success": False,
                    "error": "Dataset not found"
                }

            logger.info(f"💬 Agent-based chat request for dataset: {dataset.name} (ID: {dataset_id})")

            # Check if user is asking for visualization or analysis
            needs_visualization = any(keyword in message.lower() for keyword in [
                'visualiz', 'chart', 'graph', 'plot', 'diagram', 'show', 'display',
                'analyze', 'analysis', 'insight', 'pattern', 'trend', 'distribution',
                'correlation', 'relationship', 'compare', 'histogram', 'scatter',
                'heatmap', 'bar', 'line', 'pie'
            ])

            logger.info(f"📊 Visualization requested: {needs_visualization}")

            # Initialize visualization data
            visualizations = []
            data_analysis = {}

            # Try to load dataset data for visualization if needed
            # TEMPORARILY DISABLED to fix numpy dtype serialization issue
            if False and needs_visualization:
                try:
                    logger.info(f"📊 Loading dataset for visualization...")
                    dataset_df = await self._load_dataset_for_visualization(dataset, db)

                    if dataset_df is not None and not dataset_df.empty:
                        logger.info(f"✅ Loaded {len(dataset_df)} rows for visualization")

                        # Generate visualizations using LIDA
                        from app.services.data_visualization import get_visualization_service
                        viz_service = get_visualization_service(self.api_key)

                        # Analyze the dataset
                        data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                        logger.info(f"📊 Dataset analyzed")

                        # Generate visualizations
                        visualizations = viz_service.generate_visualizations_with_lida(
                            dataset_df,
                            query=message,
                            max_visualizations=3
                        )

                        # Convert numpy types to native Python types for JSON serialization
                        def convert_numpy_types(obj):
                            """Recursively convert numpy types to native Python types"""
                            import numpy as np
                            if isinstance(obj, (np.integer, np.int64, np.int32)):
                                return int(obj)
                            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                                return float(obj)
                            elif isinstance(obj, np.ndarray):
                                return obj.tolist()
                            elif isinstance(obj, dict):
                                return {key: convert_numpy_types(val) for key, val in obj.items()}
                            elif isinstance(obj, list):
                                return [convert_numpy_types(item) for item in obj]
                            elif isinstance(obj, (np.dtype, type)):
                                return str(obj)
                            return obj

                        # Sanitize visualization data
                        visualizations = convert_numpy_types(visualizations)
                        data_analysis = convert_numpy_types(data_analysis)

                        logger.info(f"📈 Generated {len(visualizations)} visualizations")
                    else:
                        logger.warning("⚠️  Could not load dataset data for visualization")
                except Exception as viz_error:
                    logger.error(f"❌ Visualization generation failed: {viz_error}")
                    import traceback
                    logger.error(traceback.format_exc())
                    visualizations = []
                    data_analysis = {}

            # Setup appropriate agent based on dataset type
            if dataset.is_multi_file_dataset:
                agent_result = self.setup_multi_file_agent(dataset, db)
            else:
                agent_result = self.setup_single_file_agent(dataset, db)

            if not agent_result.get("success"):
                error_msg = f"Agent setup failed: {agent_result.get('error')}"
                logger.error(error_msg)
                fallback_response = await self._chat_with_dataset_summary_fallback(
                    dataset=dataset,
                    message=message,
                    db=db,
                    start_time=start_time,
                    visualizations=visualizations,
                    data_analysis=data_analysis
                )
                if fallback_response.get("success"):
                    fallback_response["agent_error"] = error_msg
                    return fallback_response
                return {
                    "success": False,
                    "error": error_msg,
                    "message": "Failed to create agent for dataset. Please ensure MindsDB is running and configured properly."
                }

            agent_name = agent_result["agent_name"]

            # Get agent from MindsDB
            if not self._ensure_connection():
                error_msg = "Failed to connect to MindsDB"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "message": "Cannot connect to MindsDB. Please ensure MindsDB server is running."
                }

            agent = self.connection.agents.get(agent_name)

            # Prepare conversation format for agent
            conversation = [{
                'question': message,
                'answer': None
            }]

            logger.info(f"🤖 Querying agent: {agent_name}")

            # Stream response from agent
            if stream:
                try:
                    completion = agent.completion_stream(conversation)
                    full_response = ""
                    last_answer = ""

                    for chunk in completion:
                        # Handle both string and dict chunks
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get('type', '')

                            # Look for the final answer in different possible formats
                            if chunk_type == 'answer' or 'answer' in chunk:
                                # This is the final answer chunk
                                last_answer = chunk.get('answer', chunk.get('content', ''))
                            elif chunk_type == 'end' or chunk_type == 'final':
                                # End chunk might contain final answer
                                last_answer = chunk.get('content', chunk.get('text', last_answer))

                            # Always collect full response for fallback
                            chunk_text = chunk.get('content', chunk.get('text', str(chunk)))
                            full_response += str(chunk_text)
                        elif isinstance(chunk, str):
                            full_response += chunk
                        else:
                            full_response += str(chunk)

                    response_time = time.time() - start_time

                    # Try to extract clean answer from full_response if last_answer is empty
                    if not last_answer and full_response:
                        # First try to parse 'output' field from dict chunks
                        import re
                        output_match = re.search(r"'output':\s*'([^']+(?:''[^']+)*)'", full_response)
                        if not output_match:
                            output_match = re.search(r'"output":\s*"([^"]+(?:""[^"]+)*)"', full_response)

                        if output_match:
                            last_answer = output_match.group(1)
                            # Unescape any escaped quotes
                            last_answer = last_answer.replace("\\'", "'").replace('\\"', '"')

                        # Look for "Answer:" pattern in the response
                        if not last_answer and "Answer:" in full_response:
                            # Extract everything after the last "Answer:" occurrence
                            parts = full_response.split("Answer:")
                            if len(parts) > 1:
                                last_answer = parts[-1].strip()
                                # Remove trailing metadata/json
                                if last_answer:
                                    # Find the first occurrence of }{ which indicates concatenated JSON
                                    end_idx = last_answer.find('}{')
                                    if end_idx > 0:
                                        last_answer = last_answer[:end_idx]
                                    # Clean up any remaining braces or quotes at the end
                                    last_answer = last_answer.rstrip('"}')

                        # If still no clean answer, try to extract from observation/final_answer patterns
                        if not last_answer:
                            if "Observation:" in full_response:
                                parts = full_response.split("Observation:")
                                if len(parts) > 1:
                                    last_answer = parts[-1].strip()
                            elif "Final Answer:" in full_response:
                                parts = full_response.split("Final Answer:")
                                if len(parts) > 1:
                                    last_answer = parts[-1].strip()

                    # Use the clean answer if found, otherwise use full response
                    final_answer = self._clean_agent_answer(last_answer if last_answer else full_response)

                    logger.info(f"✅ Agent response complete in {response_time:.2f}s")
                    logger.info(f"📝 Extracted answer length: {len(final_answer)} chars")

                    return {
                        "success": True,
                        "answer": final_answer,
                        "source": "agent",
                        "agent_name": agent_name,
                        "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                        "tables_count": agent_result.get("tables_count", 1),
                        "response_time": response_time,
                        "streaming": True,
                        "model": self.agent_model,  # MindsDB agent model
                        # Visualization data
                        "visualizations": visualizations,
                        "data_analysis": data_analysis,
                        "has_visualizations": len(visualizations) > 0
                    }

                except Exception as e:
                    logger.error(f"Streaming failed: {e}, trying non-streaming")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Fall through to non-streaming

            # Non-streaming fallback
            try:
                completion = agent.completion(conversation)
                answer = completion.get('answer', '') if isinstance(completion, dict) else str(completion)
                answer = self._clean_agent_answer(answer)

                response_time = time.time() - start_time

                return {
                    "success": True,
                    "answer": answer,
                    "source": "agent",
                    "agent_name": agent_name,
                    "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                    "response_time": response_time,
                    "streaming": False,
                    # Visualization data
                    "visualizations": visualizations,
                    "data_analysis": data_analysis,
                    "has_visualizations": len(visualizations) > 0
                }

            except Exception as e:
                logger.error(f"Agent query failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "error": str(e),
                    "message": "Agent query failed. Please check MindsDB connection and agent configuration."
                }

        except Exception as e:
            logger.error(f"❌ Chat with agent failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "message": "Chat with dataset agent failed. Please ensure MindsDB is properly configured."
            }

    def _clean_agent_answer(self, answer: str) -> str:
        if not answer:
            return answer

        import re

        cleaned = re.sub(r"\{'type':\s*'end'[^}]*\}", "", answer).strip()
        markers = [
            "Executing final SQL query:",
            "Final Answer:",
            "Answer:",
        ]
        for marker in markers:
            if marker in cleaned:
                cleaned = cleaned.split(marker)[-1].strip()
                break

        if "|" in cleaned:
            table_start = cleaned.find("|")
            if table_start >= 0:
                cleaned = cleaned[table_start:].strip()

        return cleaned or answer

    async def _chat_with_dataset_summary_fallback(
        self,
        dataset,
        message: str,
        db,
        start_time: float,
        visualizations: Optional[List[Dict[str, Any]]] = None,
        data_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        try:
            dataset_df = await self._load_dataset_for_visualization(dataset, db)
            if dataset_df is None or dataset_df.empty:
                return {"success": False, "error": "Dataset data could not be loaded for fallback chat"}

            from app.services.data_visualization import get_visualization_service, sanitize_visualization_payload

            visualizations = visualizations or []
            data_analysis = data_analysis or {}
            if not data_analysis:
                viz_service = get_visualization_service(self.api_key)
                data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                data_analysis = sanitize_visualization_payload(data_analysis)

            answer = self._build_dataset_summary_answer(dataset, message, dataset_df, data_analysis)
            return {
                "success": True,
                "answer": answer,
                "source": "dataset_summary_fallback",
                "agent_name": "Anton",
                "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                "response_time": time.time() - start_time,
                "streaming": False,
                "model": self.agent_model,
                "visualizations": visualizations,
                "data_analysis": data_analysis,
                "has_visualizations": len(visualizations) > 0
            }
        except Exception as e:
            logger.error(f"❌ Dataset summary fallback failed: {e}")
            return {"success": False, "error": str(e)}

    def _build_dataset_summary_answer(self, dataset, message: str, dataset_df: pd.DataFrame, data_analysis: Dict[str, Any]) -> str:
        basic_stats = data_analysis.get("basic_stats", {})
        data_quality = data_analysis.get("data_quality", {})
        correlations = data_analysis.get("correlations", {})
        column_analysis = data_analysis.get("column_analysis", {})
        recommendations = data_analysis.get("recommendations", [])
        message_lower = message.lower()

        lines = [
            f'I analyzed the shared dataset "{dataset.name}".',
            "",
            "Dataset summary:",
            f"- Rows: {basic_stats.get('rows', 'unknown')}",
            f"- Columns: {basic_stats.get('columns', 'unknown')}",
        ]

        missing_values = data_quality.get("missing_values", {})
        if missing_values:
            total_missing = sum(value for value in missing_values.values() if isinstance(value, (int, float)))
            lines.append(f"- Missing values: {total_missing}")

        group_columns = [column for column in dataset_df.columns if column.lower() in message_lower]
        numeric_columns = dataset_df.select_dtypes(include=["number"]).columns.tolist()
        requested_numeric = next((column for column in numeric_columns if column.lower() in message_lower), None)
        if requested_numeric and group_columns:
            group_column = next((column for column in group_columns if column != requested_numeric), group_columns[0])
            grouped = dataset_df.groupby(group_column)[requested_numeric].sum().sort_values(ascending=False).head(10)
            lines.extend(["", f"{requested_numeric} by {group_column}:"])
            lines.extend(f"- {group}: {value:g}" for group, value in grouped.items())

        numeric_summaries = []
        for column, stats in column_analysis.items():
            if isinstance(stats, dict) and "mean" in stats:
                numeric_summaries.append(
                    f"- {column}: mean {stats.get('mean')}, min {stats.get('min')}, max {stats.get('max')}"
                )
        if numeric_summaries:
            lines.extend(["", "Numeric highlights:", *numeric_summaries[:5]])

        strong_correlations = correlations.get("strong_correlations", [])
        if strong_correlations:
            lines.append("")
            lines.append("Strong correlations:")
            for correlation in strong_correlations[:5]:
                lines.append(
                    f"- {correlation.get('column1')} and {correlation.get('column2')}: {correlation.get('correlation')}"
                )

        if recommendations:
            lines.append("")
            lines.append("Recommendations:")
            lines.extend(f"- {recommendation}" for recommendation in recommendations[:5])

        return "\n".join(lines)


# Global service instance
mindsdb_service = MindsDBService()
