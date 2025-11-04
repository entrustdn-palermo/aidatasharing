import mindsdb_sdk
import google.generativeai as genai
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

# Import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.file_handler import FileUpload

logger = logging.getLogger(__name__)


class MindsDBService:
    def __init__(self):
        # Get centralized configuration
        self.app_config = get_app_config()
        
        # Use settings from centralized configuration
        self.base_url = self.app_config.services.get_mindsdb_url()
        self.api_key = self.app_config.integrations.GOOGLE_API_KEY
        
        # Debug log the API key (masked for security)
        if self.api_key:
            masked_key = self.api_key[:4] + "..." + self.api_key[-4:] if len(self.api_key) > 8 else "***"
            logger.info(f"✅ Google API key loaded: {masked_key}")
        else:
            logger.warning("⚠️ No Google API key found in settings")
            # Try to load directly from environment
            import os
            self.api_key = os.environ.get("GOOGLE_API_KEY")
            if self.api_key:
                masked_key = self.api_key[:4] + "..." + self.api_key[-4:] if len(self.api_key) > 8 else "***"
                logger.info(f"✅ Google API key loaded from environment: {masked_key}")
            else:
                logger.error("❌ No Google API key found in environment either")
        
        # Model configurations from environment
        self.engine_name = settings.GEMINI_ENGINE_NAME
        self.default_model = settings.DEFAULT_GEMINI_MODEL
        self.chat_model_name = settings.GEMINI_CHAT_MODEL_NAME
        self.vision_model_name = settings.GEMINI_VISION_MODEL_NAME
        self.embedding_model_name = settings.GEMINI_EMBEDDING_MODEL_NAME
        
        # Configure Gemini directly as backup
        genai.configure(api_key=self.api_key)
        
        # Connection state
        self.connection = None
        self._connected = False

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
                        "rows": df.to_dict('records') if not df.empty else [],
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

    def create_gemini_engine(self) -> Dict[str, Any]:
        """Create or verify Google Gemini engine using raw SQL."""
        try:
            if not self._ensure_connection():
                return {"message": "SDK connection not available", "status": "error"}

            # Check if engine already exists first
            try:
                engines_query = "SHOW ML_ENGINES"
                result = self.connection.query(engines_query)
                engines_df = result.fetch()
                
                if not engines_df.empty:
                    for _, engine in engines_df.iterrows():
                        if engine.get('NAME') == self.engine_name:
                            logger.info(f"✅ Engine {self.engine_name} already exists")
                            return {
                                "message": f"Engine {self.engine_name} ready",
                                "status": "exists",
                                "engine_name": self.engine_name
                            }
            except Exception as e:
                logger.warning(f"⚠️ Could not check existing engines: {e}")

            # Try to use OpenAI as fallback since Gemini engine creation seems to have issues
            logger.warning(f"⚠️ Gemini engine creation having issues, trying OpenAI as fallback")
            
            # Check if we have OpenAI API key as fallback
            openai_key = getattr(settings, 'OPENAI_API_KEY', None)
            if not openai_key:
                import os
                openai_key = os.environ.get('OPENAI_API_KEY')
            
            if openai_key:
                # Try creating OpenAI engine as fallback
                openai_engine_name = "openai_engine_fallback"
                create_openai_engine_sql = f"""
                CREATE ML_ENGINE {openai_engine_name}
                FROM openai
                USING
                    api_key = '{openai_key}';
                """
                
                try:
                    logger.info(f"🔧 Creating OpenAI fallback engine: {openai_engine_name}")
                    self.connection.query(create_openai_engine_sql)
                    
                    # Wait and verify
                    import time
                    time.sleep(3)
                    
                    result = self.connection.query("SHOW ML_ENGINES")
                    engines_df = result.fetch()
                    
                    for _, engine in engines_df.iterrows():
                        if engine.get('NAME') == openai_engine_name:
                            logger.info(f"✅ OpenAI fallback engine created successfully")
                            # Update the engine name for this session
                            self.engine_name = openai_engine_name
                            return {
                                "message": f"OpenAI fallback engine {openai_engine_name} created",
                                "status": "created",
                                "engine_name": openai_engine_name
                            }
                            
                except Exception as openai_error:
                    logger.warning(f"⚠️ OpenAI fallback also failed: {openai_error}")
            
            # If all else fails, try the original Gemini approach one more time
            logger.info(f"🔧 Attempting Gemini engine creation one more time")
            create_engine_sql = f"""
            CREATE ML_ENGINE {self.engine_name}
            FROM google_gemini
            USING
                api_key = '{self.api_key}';
            """
            
            try:
                logger.info(f"🔧 Creating engine with SQL: {create_engine_sql}")
                self.connection.query(create_engine_sql)
                
                # Just return success even if we can't verify it
                # The model creation will test if it actually works
                logger.info(f"✅ Engine creation command executed")
                return {
                    "message": f"Engine {self.engine_name} creation attempted",
                    "status": "created",
                    "engine_name": self.engine_name
                }
                    
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"✅ Engine {self.engine_name} already exists")
                    return {
                        "message": f"Engine {self.engine_name} ready",
                        "status": "exists",
                        "engine_name": self.engine_name
                    }
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ Failed to create/verify engine {self.engine_name}: {e}")
            return {
                "message": f"Engine creation failed: {str(e)}",
                "status": "error",
                "engine_name": self.engine_name
            }

    def create_gemini_model(
        self, 
        model_name: str, 
        model_type: str = "chat",
        column_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a Gemini model using raw SQL."""
        try:
            if not self._ensure_connection():
                return {"message": "SDK connection not available", "status": "error"}

            # Ensure engine exists first
            engine_result = self.create_gemini_engine()
            if engine_result.get("status") == "error":
                return {"message": "Engine creation failed", "status": "error"}

            # Check if model already exists
            try:
                models_query = "SHOW MODELS"
                result = self.connection.query(models_query)
                models_df = result.fetch()
                
                if not models_df.empty:
                    for _, model in models_df.iterrows():
                        if model.get('NAME') == model_name:
                            model_status = model.get('STATUS', 'Unknown')
                            logger.info(f"✅ Model {model_name} already exists (Status: {model_status})")
                            return {
                                "message": f"Model {model_name} ready",
                                "status": "exists",
                                "model_name": model_name
                            }
            except Exception as e:
                logger.warning(f"⚠️ Could not check existing models: {e}")

            # Set default column name
            if not column_name:
                column_name = "question"

            # Determine which engine to use and appropriate model syntax
            engine_name = self.engine_name
            model_sql = ""
            
            if "openai" in engine_name.lower():
                # OpenAI model syntax
                model_sql = f"""
                CREATE MODEL {model_name}
                PREDICT response
                USING
                    engine = '{engine_name}',
                    model_name = 'gpt-3.5-turbo',
                    prompt_template = 'Answer the following question: {{{{question}}}}';
                """
            else:
                # Gemini model syntax
                model_sql = f"""
                CREATE MODEL {model_name}
                PREDICT response
                USING
                    engine = '{engine_name}',
                    model_name = '{self.default_model}',
                    prompt_template = 'Answer the following question: {{{{question}}}}';
                """
            
            try:
                logger.info(f"🤖 Creating model with SQL: {model_sql}")
                self.connection.query(model_sql)
                
                # Wait for model to initialize
                import time
                logger.info(f"⏳ Waiting for model {model_name} to initialize...")
                time.sleep(8)  # Increased wait time
                
                # Verify model was created and check its status
                result = self.connection.query("SHOW MODELS")
                models_df = result.fetch()
                
                model_found = False
                model_status = "Unknown"
                if not models_df.empty:
                    for _, model in models_df.iterrows():
                        if model.get('NAME') == model_name:
                            model_found = True
                            model_status = model.get('STATUS', 'Unknown')
                            logger.info(f"✅ Model {model_name} found with status: {model_status}")
                            break
                
                if model_found:
                    return {
                        "message": f"Model {model_name} created successfully (Status: {model_status})",
                        "status": "created",
                        "model_name": model_name,
                        "engine": engine_name,
                        "column": column_name,
                        "model": self.default_model,
                        "model_status": model_status
                    }
                else:
                    # Even if we can't find it in SHOW MODELS, return success
                    # The actual chat test will determine if it works
                    logger.warning(f"⚠️ Model {model_name} not found in SHOW MODELS but creation command succeeded")
                    return {
                        "message": f"Model {model_name} creation attempted",
                        "status": "created",
                        "model_name": model_name,
                        "engine": engine_name,
                        "column": column_name,
                        "model": self.default_model,
                        "model_status": "unknown"
                    }
                
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"✅ Model {model_name} already exists")
                    return {
                        "message": f"Model {model_name} ready",
                        "status": "exists",
                        "model_name": model_name
                    }
                else:
                    raise e
            
        except Exception as e:
            logger.error(f"❌ Failed to create model {model_name}: {e}")
            return {
                "message": f"Model creation failed: {str(e)}",
                "status": "error",
                "model_name": model_name
            }

    def ai_chat(self, message: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Handle AI chat using direct Google Gemini API as fallback when MindsDB models fail."""
        if not model_name:
            model_name = self.chat_model_name

        try:
            # First try MindsDB approach
            if self._ensure_connection() and self.connection:
                try:
                    logger.info(f"💬 Attempting MindsDB chat with model: {model_name}")
                    
                    # First ensure the model exists and is ready
                    model_result = self.create_gemini_model(model_name)
                    if model_result.get("status") == "error":
                        logger.warning(f"⚠️ MindsDB model creation failed: {model_result.get('message')}")
                        raise Exception(f"Model creation failed: {model_result.get('message')}")
                    
                    # Wait a moment for the model to be ready
                    import time
                    time.sleep(2)
                    
                    # Query the model using MindsDB
                    query = f"""
                    SELECT response 
                    FROM {model_name} 
                    WHERE question = '{message.replace("'", "''")}'
                    """
                    
                    logger.info(f"🔍 Executing MindsDB query: {query}")
                    result = self.connection.query(query)
                    
                    if result:
                        try:
                            if hasattr(result, 'fetch'):
                                rows = result.fetch()
                                if hasattr(rows, 'empty') and not rows.empty:
                                    rows = rows.to_dict('records')
                                elif not isinstance(rows, list):
                                    rows = [rows] if rows is not None else []
                            else:
                                rows = []
                            
                            if rows and len(rows) > 0:
                                row_data = rows[0]
                                answer = ""
                                
                                if isinstance(row_data, dict):
                                    answer = row_data.get('response', '')
                                else:
                                    answer = str(row_data)
                                
                                if not isinstance(answer, str):
                                    answer = str(answer)
                                
                                # Clean up the response format
                                if answer.startswith("{0: '") and answer.endswith("'}"):
                                    answer = answer[5:-2]
                                elif answer.startswith("{0: \"") and answer.endswith("\"}"):
                                    answer = answer[5:-2]
                                
                                answer = answer.replace('\\n', '\n').strip()
                                
                                if answer and answer.strip():
                                    logger.info(f"✅ MindsDB chat successful")
                                    return {
                                        "answer": answer,
                                        "model": f"{model_name} (MindsDB)",
                                        "timestamp": datetime.utcnow().isoformat(),
                                        "tokens_used": len(message.split()) + len(answer.split()),
                                        "source": "mindsdb"
                                    }
                                else:
                                    logger.warning(f"⚠️ MindsDB returned empty response")
                                    raise Exception("Empty response from MindsDB")
                            else:
                                logger.warning(f"⚠️ MindsDB returned no rows")
                                raise Exception("No rows returned from MindsDB")
                                
                        except Exception as fetch_error:
                            logger.warning(f"⚠️ MindsDB fetch error: {fetch_error}")
                            raise Exception(f"MindsDB fetch failed: {fetch_error}")
                
                except Exception as mindsdb_error:
                    logger.warning(f"⚠️ MindsDB chat failed: {mindsdb_error}")
                    # Fall through to direct API approach
            
            # Fallback to direct Google Gemini API
            logger.info(f"🔄 Using direct Google Gemini API as fallback")
            
            if not self.api_key:
                raise Exception("No Google API key available for direct API access")
            
            import google.generativeai as genai
            
            # Configure Gemini API
            genai.configure(api_key=self.api_key)
            
            # Use model from environment configuration
            model = genai.GenerativeModel(self.default_model)
            
            # Generate response
            response = model.generate_content(message)
            
            if response and response.text:
                logger.info(f"✅ Direct Google API chat successful")
                return {
                    "answer": response.text.strip(),
                    "model": f"{self.default_model} (Direct API)",
                    "timestamp": datetime.utcnow().isoformat(),
                    "tokens_used": len(message.split()) + len(response.text.split()),
                    "source": "google_direct_api"
                }
            else:
                raise Exception("No response from Google API")

        except Exception as e:
            logger.error(f"❌ AI chat failed completely: {e}")
            return {
                "answer": f"I'm sorry, but I encountered an error while processing your question: {str(e)}",
                "error": f"Chat failed: {str(e)}",
                "model": "Error Handler",
                "timestamp": datetime.utcnow().isoformat(),
                "source": "error"
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
                        "rows": df.to_dict('records') if not df.empty else [],
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
                        "sample_data": df.head(3).to_dict('records'),
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
                    sample_data = df.head(5).to_dict('records')
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

    def _check_if_file_needs_mindsdb_setup(self, dataset, file_upload) -> bool:
        """Check if a file dataset needs MindsDB processing setup."""
        try:
            # Check if dataset already has MindsDB processing configured
            if (dataset.ai_processing_status == "ready" and 
                dataset.mindsdb_table_name and 
                dataset.mindsdb_database):
                logger.info(f"✅ Dataset {dataset.id} already has MindsDB setup")
                return False
            
            # Check if file type is supported for automatic processing
            if not file_upload:
                logger.info(f"⚠️ No file upload record found for dataset {dataset.id}")
                return False
            
            file_ext = os.path.splitext(file_upload.original_filename.lower())[1]
            supported_extensions = {'.csv', '.xlsx', '.xls', '.json', '.txt', '.pdf', '.parquet'}
            
            if file_ext not in supported_extensions:
                logger.info(f"⚠️ File type {file_ext} not supported for automatic MindsDB setup")
                return False
            
            logger.info(f"🔄 Dataset {dataset.id} needs MindsDB setup for file type {file_ext}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking MindsDB setup needs for dataset {dataset.id}: {e}")
            return False

    def _setup_file_processing_automatically(self, dataset, file_upload, db_session) -> Dict[str, Any]:
        """Automatically set up MindsDB processing for a file dataset."""
        try:
            logger.info(f"🚀 Starting automatic MindsDB setup for dataset {dataset.id}")
            
            # Determine file type
            file_ext = os.path.splitext(file_upload.original_filename.lower())[1].lstrip('.')
            file_type_map = {
                'csv': 'csv',
                'xlsx': 'xlsx', 
                'xls': 'xls',
                'json': 'json',
                'txt': 'txt',
                'pdf': 'pdf',
                'parquet': 'parquet'
            }
            file_type = file_type_map.get(file_ext, file_ext)
            
            # Generate names
            file_name = f"dataset_{dataset.id}_{file_type}"
            model_name = f"{file_name}_model"
            
            # Step 1: Upload file to MindsDB
            upload_result = self._upload_file_to_mindsdb_internal(file_upload.file_path, file_name, file_ext)
            if not upload_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to upload file to MindsDB: {upload_result.get('error')}"
                }
            
            # Step 2: Create appropriate model
            model_result = self._create_model_for_file_internal(file_name, file_type)
            if not model_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to create MindsDB model: {model_result.get('error')}"
                }
            
            # Step 3: Update dataset with MindsDB information
            try:
                dataset.mindsdb_table_name = model_name
                dataset.mindsdb_database = "mindsdb"
                dataset.ai_processing_status = "ready"
                dataset.ai_chat_enabled = True
                
                # Update chat context
                if not dataset.chat_context:
                    dataset.chat_context = {}
                
                dataset.chat_context.update({
                    'mindsdb_datasource': file_name,
                    'mindsdb_available': True,
                    'model_name': model_name,
                    'file_type': file_type,
                    'auto_setup_completed': True,
                    'auto_setup_timestamp': datetime.utcnow().isoformat()
                })
                
                db_session.commit()
                
                logger.info(f"✅ Successfully set up automatic MindsDB processing for dataset {dataset.id}")
                return {
                    "success": True,
                    "model_name": model_name,
                    "file_name": file_name,
                    "file_type": file_type
                }
                
            except Exception as update_error:
                logger.error(f"❌ Failed to update dataset {dataset.id} with MindsDB info: {update_error}")
                db_session.rollback()
                return {
                    "success": False,
                    "error": f"Failed to update dataset: {str(update_error)}"
                }
        
        except Exception as e:
            logger.error(f"❌ Error in automatic MindsDB setup for dataset {dataset.id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _upload_file_to_mindsdb_internal(self, file_path: str, file_name: str, file_ext: str) -> Dict[str, Any]:
        """Internal method to upload file to MindsDB."""
        try:
            # Try multiple possible paths to find the file
            possible_paths = [
                file_path,
                os.path.join("/Users/syaikhipin/Documents/program/simpleaisharing/backend", file_path.lstrip("./")),
                os.path.join("/Users/syaikhipin/Documents/program/simpleaisharing", file_path.lstrip("./")),
                os.path.join("/Users/syaikhipin/Documents/program/simpleaisharing/storage", file_path.split('/')[-1]),
            ]
            
            actual_file_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    actual_file_path = path
                    break
            
            if not actual_file_path:
                return {"success": False, "error": f"File not found at any of these paths: {possible_paths}"}
            
            # MIME type mapping
            mime_types = {
                'csv': 'text/csv',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'xls': 'application/vnd.ms-excel',
                'json': 'application/json',
                'txt': 'text/plain',
                'pdf': 'application/pdf',
                'parquet': 'application/octet-stream'
            }
            mime_type = mime_types.get(file_ext, 'application/octet-stream')
            
            # Upload to MindsDB via API
            mindsdb_url = self.base_url
            
            with open(actual_file_path, 'rb') as f:
                files = {'file': (file_name + '.' + file_ext, f, mime_type)}
                response = requests.put(
                    f"{mindsdb_url}/api/files/{file_name}",
                    files=files,
                    timeout=30
                )
            
            if response.status_code == 200:
                logger.info(f"✅ Successfully uploaded file to MindsDB: {file_name}")
                return {"success": True, "file_name": file_name}
            else:
                logger.error(f"❌ Failed to upload file to MindsDB: {response.status_code} - {response.text}")
                return {"success": False, "error": f"Upload failed: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ Error uploading file to MindsDB: {e}")
            return {"success": False, "error": str(e)}

    def _create_model_for_file_internal(self, file_name: str, file_type: str) -> Dict[str, Any]:
        """Internal method to create MindsDB model for a file."""
        try:
            if not self._ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}
            
            # Test file accessibility
            test_query = f"SELECT * FROM files.{file_name} LIMIT 1"
            try:
                result = self.connection.query(test_query)
                logger.info(f"✅ File {file_name} is accessible in MindsDB")
            except Exception as e:
                logger.error(f"❌ Cannot access file {file_name} in MindsDB: {e}")
                return {"success": False, "error": f"File not accessible: {str(e)}"}
            
            model_name = f"{file_name}_model"
            
            # Create model based on file type
            if file_type in ['pdf', 'txt']:
                # RAG model for text-based files
                model_sql = f"""
                CREATE MODEL mindsdb.{model_name}
                FROM files 
                    (SELECT * FROM {file_name})
                PREDICT answer
                USING
                   engine="rag",
                   llm_type="openai",
                   input_column='question';
                """
                model_type = "RAG"
                
            elif file_type in ['csv', 'xlsx', 'xls', 'json', 'parquet']:
                # Knowledge base for structured data
                model_sql = f"""
                CREATE KNOWLEDGE_BASE mindsdb.{model_name}
                FROM files.{file_name}
                USING
                   model='text-embedding-ada-002',
                   storage=mindsdb;
                """
                model_type = "Knowledge Base"
            else:
                return {"success": False, "error": f"Unsupported file type for model creation: {file_type}"}
            
            logger.info(f"🤖 Creating {model_type} model: {model_name}")
            
            try:
                result = self.connection.query(model_sql)
                logger.info(f"✅ {model_type} model created successfully: {model_name}")
                return {
                    "success": True,
                    "model_name": model_name,
                    "model_type": model_type
                }
            except Exception as model_error:
                logger.error(f"❌ Failed to create model: {model_error}")
                return {"success": False, "error": f"Model creation failed: {str(model_error)}"}
                
        except Exception as e:
            logger.error(f"❌ Error creating model for file {file_name}: {e}")
            return {"success": False, "error": str(e)}

    def create_file_database_connector(self, file_upload: "FileUpload") -> Dict[str, Any]:
        """Create MindsDB database connector for uploaded files to make them accessible."""
        try:
            if not self._ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Generate clean database name and file name for MindsDB
            clean_name = f"file_db_{file_upload.id}"
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

            # Create database connector using files engine with uploaded file
            connection_params = {"file": uploaded_file_name}
            engine = "files"

            # Create the database connector using MindsDB SQL
            create_db_sql = f"""
            CREATE DATABASE IF NOT EXISTS {clean_name}
            WITH ENGINE = '{engine}',
            PARAMETERS = {json.dumps(connection_params)};
            """
            
            logger.info(f"🗄️ Creating file database connector: {clean_name}")
            logger.info(f"📄 SQL: {create_db_sql}")
            
            try:
                result = self.connection.query(create_db_sql)
                logger.info(f"✅ File database connector {clean_name} created successfully")
                
                # Test the connector by trying to fetch data
                test_result = self.test_file_database_connector(clean_name, file_upload)
                
                return {
                    "success": True,
                    "database_name": clean_name,
                    "engine": engine,
                    "file_path": file_upload.file_path,
                    "file_type": file_ext,
                    "uploaded_filename": uploaded_file_name,  # Return the uploaded filename
                    "test_result": test_result,
                    "message": f"File database connector {clean_name} created successfully"
                }
                
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"✅ File database connector {clean_name} already exists")
                    return {
                        "success": True,
                        "database_name": clean_name,
                        "engine": engine,
                        "file_path": file_upload.file_path,
                        "file_type": file_ext,
                        "message": f"File database connector {clean_name} already exists"
                    }
                else:
                    raise e
                    
        except Exception as e:
            logger.error(f"❌ Failed to create file database connector for {file_upload.original_filename}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_upload_id": file_upload.id
            }

    def test_file_database_connector(self, database_name: str, file_upload: "FileUpload") -> Dict[str, Any]:
        """Test a file database connector by fetching sample data."""
        try:
            if not self._ensure_connection():
                return {"success": False, "error": "MindsDB connection not available"}

            # Try different table names that MindsDB might use for file data
            possible_table_names = [
                file_upload.original_filename.split('.')[0],  # filename without extension
                "data",  # common default
                "file",  # another common default
                f"uploaded_file_{file_upload.id}"  # our custom name
            ]
            
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
                                "sample_data": df.head(3).to_dict('records')
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

    def chat_with_dataset(self, dataset_id: str, message: str, user_id: Optional[int] = None, session_id: Optional[str] = None, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """Chat with dataset using MindsDB connectors, native AI models, and data visualization."""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"🔍 Starting chat_with_dataset for dataset_id={dataset_id}, message='{message[:50]}...'")
            
            # Get dataset information from database
            dataset = None
            dataset_context = ""
            is_web_connector = False
            web_connector_info = {}
            visualizations = []
            data_analysis = {}
            dataset_df = None
            
            try:
                from app.core.database import get_db
                from app.models.dataset import Dataset
                from sqlalchemy.orm import Session
                
                db = next(get_db())
                dataset = db.query(Dataset).filter(Dataset.id == int(dataset_id)).first()
                
                if not dataset:
                    logger.error(f"❌ Dataset with ID {dataset_id} not found")
                    return {
                        "error": f"Dataset with ID {dataset_id} not found",
                        "answer": "I couldn't find the dataset you're referring to. Please check the dataset ID.",
                        "dataset_id": dataset_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                logger.info(f"🔍 Processing chat for dataset: {dataset.name} (ID: {dataset_id})")
                
                # Check if user is asking for visualization or analysis
                needs_visualization = any(keyword in message.lower() for keyword in [
                    'visualiz', 'chart', 'graph', 'plot', 'diagram', 'show', 'display',
                    'analyze', 'analysis', 'insight', 'pattern', 'trend', 'distribution',
                    'correlation', 'relationship', 'compare', 'histogram', 'scatter',
                    'heatmap', 'bar', 'line', 'pie'
                ])
                
                # Try to load dataset data for visualization if needed
                if needs_visualization:
                    try:
                        dataset_df = self._load_dataset_for_visualization(dataset, db)
                        if dataset_df is not None and not dataset_df.empty:
                            logger.info(f"📊 Loaded dataset with {len(dataset_df)} rows for visualization")
                            
                            # Generate visualizations using LIDA
                            from app.services.data_visualization import get_visualization_service
                            viz_service = get_visualization_service(self.api_key)
                            
                            # Analyze the dataset
                            data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                            
                            # Generate visualizations
                            visualizations = viz_service.generate_visualizations_with_lida(
                                dataset_df,
                                query=message,
                                max_visualizations=3
                            )
                            
                            logger.info(f"📈 Generated {len(visualizations)} visualizations")
                        else:
                            logger.warning("Could not load dataset data for visualization")
                    except Exception as viz_error:
                        logger.error(f"Error generating visualizations: {viz_error}")
                        visualizations = []
                        data_analysis = {}
                
                # Check if this is a web connector dataset (only if it has a connector_id and actual API URL)
                if dataset.connector_id and dataset.source_url and (
                    dataset.source_url.startswith('http://') or 
                    dataset.source_url.startswith('https://') or
                    dataset.source_url.startswith('api://')
                ):
                    is_web_connector = True
                    web_connector_info = {
                        "connector_id": dataset.connector_id,
                        "source_url": dataset.source_url,
                        "connector_name": getattr(dataset, 'connector_name', None)
                    }
                    logger.info(f"🌐 Detected web connector dataset: {web_connector_info}")
                else:
                    # This is an uploaded file dataset
                    logger.info(f"📁 Detected uploaded file dataset: {dataset.name} (type: {dataset.type})")
                
            except Exception as db_error:
                logger.error(f"❌ Could not load dataset from database: {db_error}")
                return {
                    "error": f"Database error: {str(db_error)}",
                    "answer": "I encountered a database error while trying to access the dataset.",
                    "dataset_id": dataset_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            # Ensure MindsDB connection
            logger.info("🔗 Checking MindsDB connection...")
            if not self._ensure_connection():
                logger.error("❌ MindsDB connection failed")
                return {
                    "error": "MindsDB connection failed",
                    "answer": "I couldn't connect to MindsDB to process your request. Please try again later.",
                    "dataset_id": dataset_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            logger.info("✅ MindsDB connection established")
            
            # Build enhanced dataset context based on type
            if is_web_connector:
                dataset_context = f"""
                Dataset Information (Web Connector):
                - Name: {dataset.name}
                - Type: {dataset.type} (Web API Data)
                - Description: {dataset.description or 'No description available'}
                - Data Source: External API via web connector
                - Source URL: {dataset.source_url}
                - Connector ID: {dataset.connector_id}
                - Rows: {dataset.row_count or 'Dynamic (API-dependent)'}
                - Columns: {dataset.column_count or 'Dynamic (API-dependent)'}
                - Created: {dataset.created_at}
                - Data Access: Real-time via MindsDB web connector
                - Data Freshness: Live data from API endpoint
                """
                
                # Try to get fresh sample data from the web connector
                try:
                    clean_dataset = dataset.name.lower().replace(' ', '_').replace('-', '_')
                    sample_query = f"SELECT * FROM {clean_dataset}_view LIMIT 5"
                    sample_result = self.connection.query(sample_query)
                    
                    if sample_result and hasattr(sample_result, 'fetch'):
                        sample_df = sample_result.fetch()
                        if not sample_df.empty:
                            sample_data = sample_df.to_dict('records')
                            dataset_context += f"\n- Current Sample Data: {sample_data[:2]}"  # Show first 2 rows
                            dataset_context += f"\n- Available Columns: {list(sample_df.columns)}"
                            logger.info(f"📊 Retrieved fresh sample data from web connector")
                        else:
                            dataset_context += "\n- Sample Data: No data currently available from API"
                    else:
                        dataset_context += "\n- Sample Data: Unable to fetch current data"
                        
                except Exception as sample_error:
                    logger.warning(f"⚠️ Could not fetch sample data from web connector: {sample_error}")
                    dataset_context += "\n- Sample Data: Unable to fetch current data from web connector"
                    
            else:
                # For uploaded files, ensure they have a database connector
                logger.info(f"🗄️ Processing uploaded file dataset: {dataset.name}")

                # Check if this is a multi-file dataset
                if dataset.is_multi_file_dataset:
                    logger.info(f"📁 Processing multi-file dataset with {dataset.total_files_count or 'multiple'} files")
                    
                    # Get the primary file for multi-file datasets
                    from app.models.dataset import DatasetFile
                    dataset_files = db.query(DatasetFile).filter(
                        DatasetFile.dataset_id == dataset.id,
                        DatasetFile.is_deleted == False
                    ).order_by(DatasetFile.is_primary.desc(), DatasetFile.file_order.asc()).all()
                    
                    if dataset_files:
                        primary_file = next((f for f in dataset_files if f.is_primary), dataset_files[0])
                        logger.info(f"📄 Using primary file for chat: {primary_file.filename}")
                        
                        # Build context for multi-file dataset
                        file_list = "\n".join([f"  - {f.filename} ({f.file_type}, {'Primary' if f.is_primary else 'Supporting'})" for f in dataset_files[:10]])
                        if len(dataset_files) > 10:
                            file_list += f"\n  ... and {len(dataset_files) - 10} more files"
                        
                        dataset_context = f"""
                Dataset Information (Multi-File Dataset):
                - Name: {dataset.name}
                - Type: Multi-file dataset ({len(dataset_files)} files)
                - Description: {dataset.description or 'No description available'}
                - Primary File: {primary_file.filename} ({primary_file.file_type})
                - Total Files: {len(dataset_files)}
                - Files in Dataset:
{file_list}
                - Created: {dataset.created_at}
                - Data Access: Analysis based on primary file content
                - Note: This is a multi-file dataset. The AI analysis is primarily based on the primary file ({primary_file.filename}).
                       Other files in the dataset provide supporting context but are not directly analyzed in this chat.
                """
                        
                        # Try to get file upload record for the primary file
                        from app.models.file_handler import FileUpload
                        file_upload = db.query(FileUpload).filter(
                            FileUpload.dataset_id == dataset.id,
                            FileUpload.original_filename == primary_file.filename
                        ).first()
                        
                        if not file_upload:
                            # Fallback to any file upload for this dataset
                            file_upload = db.query(FileUpload).filter(
                                FileUpload.dataset_id == dataset.id
                            ).first()
                    else:
                        logger.warning(f"⚠️ No files found for multi-file dataset {dataset.id}")
                        dataset_context = f"""
                Dataset Information (Multi-File Dataset):
                - Name: {dataset.name}
                - Type: Multi-file dataset
                - Description: {dataset.description or 'No description available'}
                - Created: {dataset.created_at}
                - Warning: No files found in this multi-file dataset
                """
                        file_upload = None
                else:
                    # Single file dataset - original logic
                    from app.models.file_handler import FileUpload
                    file_upload = db.query(FileUpload).filter(
                        FileUpload.dataset_id == dataset.id
                    ).first()
                
                # Process file upload if found (for both single and multi-file datasets)
                if file_upload:
                    logger.info(f"📁 Found file upload record: {file_upload.original_filename}")
                    
                    # Check if file needs MindsDB processing setup and do it automatically
                    needs_setup = self._check_if_file_needs_mindsdb_setup(dataset, file_upload)
                    
                    if needs_setup:
                        logger.info(f"🔄 File processing not set up yet, automatically setting up MindsDB processing...")
                        setup_result = self._setup_file_processing_automatically(dataset, file_upload, db)
                        
                        if setup_result.get("success"):
                            logger.info(f"✅ Automatic MindsDB setup completed: {setup_result.get('model_name')}")
                            # Refresh dataset to get updated info
                            db.refresh(dataset)
                        else:
                            logger.warning(f"⚠️ Automatic MindsDB setup failed: {setup_result.get('error')}")
                    
                    # Create database connector for this file if it doesn't exist
                    connector_result = self.create_file_database_connector(file_upload)
                    
                    if connector_result.get("success"):
                        logger.info(f"✅ Database connector ready: {connector_result.get('database_name')}")
                        
                        # Try to get sample data from the file database
                        database_name = connector_result.get("database_name")
                        test_result = connector_result.get("test_result", {})
                        
                        if test_result.get("success") and test_result.get("sample_data"):
                            sample_data = test_result.get("sample_data", [])
                            columns = test_result.get("columns", [])
                            
                            # Update dataset_context if not already set for multi-file
                            if not dataset.is_multi_file_dataset:
                                dataset_context = f"""
                Dataset Information (Uploaded File):
                - Name: {dataset.name}
                - Type: {dataset.type}
                - Description: {dataset.description or 'No description available'}
                - Data Source: Uploaded file ({file_upload.original_filename})
                - File Size: {file_upload.file_size} bytes
                - Rows: {dataset.row_count or test_result.get('rows_retrieved', 'Unknown')}
                - Columns: {dataset.column_count or len(columns)}
                - Created: {dataset.created_at}
                - Data Access: Static file data via MindsDB file connector
                - Database Name: {database_name}
                - Available Columns: {columns}
                - Sample Data: {sample_data[:2] if sample_data else 'No sample data available'}
                """
                        else:
                            # Update dataset_context if not already set for multi-file
                            if not dataset.is_multi_file_dataset:
                                dataset_context = f"""
                Dataset Information (Uploaded File):
                - Name: {dataset.name}
                - Type: {dataset.type}
                - Description: {dataset.description or 'No description available'}
                - Data Source: Uploaded file ({file_upload.original_filename})
                - File Size: {file_upload.file_size} bytes
                - Rows: {dataset.row_count or 'Unknown'}
                - Columns: {dataset.column_count or 'Unknown'}
                - Created: {dataset.created_at}
                - Data Access: Static file data via MindsDB file connector
                - Database Name: {database_name}
                - Note: Database connector created but data access needs verification
                """
                    else:
                        logger.warning(f"⚠️ Failed to create database connector: {connector_result.get('error')}")
                        # Update dataset_context if not already set for multi-file
                        if not dataset.is_multi_file_dataset:
                            dataset_context = f"""
                Dataset Information (Uploaded File):
                - Name: {dataset.name}
                - Type: {dataset.type}
                - Description: {dataset.description or 'No description available'}
                - Data Source: Uploaded file ({file_upload.original_filename})
                - File Size: {file_upload.file_size} bytes
                - Rows: {dataset.row_count or 'Unknown'}
                - Columns: {dataset.column_count or 'Unknown'}
                - Created: {dataset.created_at}
                - Data Access: File data (connector creation failed)
                - Warning: Database connector could not be created - {connector_result.get('error')}
                """
                else:
                    logger.warning(f"⚠️ No file upload record found for dataset {dataset.id}")
                    # Only set dataset_context if not already set for multi-file
                    if not dataset.is_multi_file_dataset or 'dataset_context' not in locals():
                        dataset_context = f"""
                Dataset Information (Uploaded File):
                - Name: {dataset.name}
                - Type: {dataset.type}
                - Description: {dataset.description or 'No description available'}
                - Data Source: Uploaded file
                - Rows: {dataset.row_count or 'Unknown'}
                - Columns: {dataset.column_count or 'Unknown'}
                - Created: {dataset.created_at}
                - Data Access: Static file data
                - Warning: File upload record not found
                """
            
            # Build enhanced prompt based on dataset type
            if is_web_connector:
                enhanced_message = f"""
                You are an expert data analyst with access to a live API dataset through MindsDB web connectors. Your role is to provide comprehensive, actionable insights with detailed analysis and real-time data understanding.

                LIVE API DATASET INFORMATION:
                {dataset_context}

                USER QUESTION: {message}

                IMPORTANT CONTEXT FOR WEB CONNECTOR DATASETS:
                - This dataset contains LIVE data from an external API endpoint
                - Data may change between queries as it's fetched in real-time
                - The data structure and content depend on the API's current response
                - You have access to the most current data available from the API
                - Consider API limitations, rate limits, and data freshness in your analysis

                INSTRUCTIONS FOR YOUR RESPONSE:
                1. **Live Data Understanding**: Explain that this is real-time API data and its implications
                2. **Current Data Analysis**: Provide analysis based on the most recent data available
                3. **API Data Patterns**: Identify patterns specific to API-sourced data
                4. **Real-time Insights**: Focus on insights that leverage the live nature of the data
                5. **Data Freshness**: Comment on data recency and potential changes over time
                6. **API Considerations**: Note any API-specific limitations or characteristics

                RESPONSE FORMAT:
                Please structure your response using clear markdown formatting with the following sections:

                ## 🌐 Live API Dataset Overview
                [Description of the real-time dataset and its API source characteristics]

                ## 🎯 Current Data Analysis
                [Analysis based on the most recent data from the API]

                ## 📊 Real-time Data Patterns
                [Patterns and trends specific to this live API data]

                ## 📈 Dynamic Insights
                [Insights that leverage the real-time nature of the data]

                ## 🔄 Data Freshness & Reliability
                [Information about data recency and API reliability]

                ## 💡 API-Aware Recommendations
                [Recommendations that consider the live, API-based nature of the data]

                ## ⚠️ API Limitations & Considerations
                [Any API-specific limitations, rate limits, or data quality considerations]

                Focus on providing insights that are enhanced by the real-time, API-based nature of this dataset. Emphasize current data states and dynamic analysis capabilities.
                """
            else:
                enhanced_message = f"""
                You are an expert data analyst with access to a specific uploaded dataset. Your role is to provide comprehensive, actionable insights with detailed analysis and visualization recommendations.

                DATASET INFORMATION:
                {dataset_context}

                USER QUESTION: {message}

                INSTRUCTIONS FOR YOUR RESPONSE:
                1. **Data Understanding**: First, clearly explain what this dataset contains and its structure
                2. **Direct Answer**: Provide a specific, detailed answer to the user's question based on the actual data
                3. **Statistical Analysis**: Include relevant statistics, patterns, and trends you can identify
                4. **Visualization Recommendations**: Suggest specific charts and graphs that would best represent the data for this question
                5. **Actionable Insights**: Provide practical insights and recommendations based on your analysis
                6. **Data Quality Notes**: Comment on any data quality issues or limitations you observe

                RESPONSE FORMAT:
                Please structure your response using clear markdown formatting with the following sections:

                ## 📊 Data Overview
                [Brief description of the dataset and its key characteristics]

                ## 🎯 Analysis Results
                [Direct answer to the user's question with specific findings]

                ## 📈 Statistical Insights
                [Key statistics, patterns, and trends identified]

                ## 📋 Recommended Visualizations
                [Specific chart types and visualization suggestions with reasoning]

                ## 💡 Key Insights & Recommendations
                [Actionable insights and practical recommendations]

                ## ⚠️ Data Quality & Limitations
                [Any limitations or data quality considerations]

                Be specific, use actual data values when available, and ensure your analysis is thorough and professional. Focus on providing value through deep data understanding rather than generic responses.
                """
            
            logger.info(f"💬 Using {'web connector enhanced' if is_web_connector else 'general'} chat model: {self.chat_model_name}")
            
            # Use existing general chat model with enhanced context
            result = self.ai_chat(enhanced_message, model_name=self.chat_model_name)
            
            if result and isinstance(result, dict) and result.get("answer"):
                response_time = time.time() - start_time
                
                # Add visualization data if available
                if visualizations:
                    result["visualizations"] = visualizations
                    result["data_analysis"] = data_analysis
                    result["has_visualizations"] = True
                    
                    # Enhance the answer with visualization insights
                    viz_summary = f"\n\n📊 **Data Visualizations Generated:**\n"
                    for i, viz in enumerate(visualizations, 1):
                        viz_summary += f"{i}. {viz.get('title', 'Visualization')}\n"
                    
                    if data_analysis and data_analysis.get('recommendations'):
                        viz_summary += f"\n📌 **Key Recommendations:**\n"
                        for rec in data_analysis['recommendations'][:3]:
                            viz_summary += f"• {rec}\n"
                    
                    result["answer"] = result["answer"] + viz_summary
                
                result.update({
                    "dataset_id": dataset_id,
                    "dataset_name": dataset.name,
                    "model": f"enhanced_{self.chat_model_name}",
                    "source": "mindsdb_web_connector_chat" if is_web_connector else "mindsdb_enhanced_chat",
                    "is_web_connector": is_web_connector,
                    "web_connector_info": web_connector_info if is_web_connector else None,
                    "response_time_seconds": response_time,
                    "user_id": user_id,
                    "session_id": session_id,
                    "organization_id": organization_id or dataset.organization_id,
                    "has_visualizations": len(visualizations) > 0 if visualizations else False
                })
                
                logger.info(f"✅ Successfully processed {'web connector' if is_web_connector else 'standard'} dataset chat in {response_time:.2f}s")
                return result
            else:
                logger.error("❌ AI chat returned no valid response")
                return {
                    "error": "AI chat failed",
                    "answer": "I'm sorry, but I couldn't process your question at this time. Please try again.",
                    "dataset_id": dataset_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"❌ Dataset chat failed: {e}")
            return {
                "error": f"Dataset chat failed: {str(e)}",
                "answer": "I'm sorry, but I encountered an error while processing your question.",
                "dataset_id": dataset_id,
                "timestamp": datetime.utcnow().isoformat()
            }

    def create_dataset_ml_model(
        self, 
        dataset_id: int, 
        dataset_name: str, 
        dataset_type: str, 
        dataset_content: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create ML models for a dataset (chat model with Gemini)."""
        try:
            logger.info(f"🤖 Creating ML models for dataset {dataset_id} ({dataset_name})")
            
            # Ensure MindsDB connection
            if not self._ensure_connection():
                logger.error("❌ MindsDB connection failed")
                return {
                    "success": False,
                    "error": "MindsDB connection failed",
                    "dataset_id": dataset_id
                }
            
            # Clean dataset name for MindsDB model naming
            clean_dataset_name = dataset_name.lower().replace(' ', '_').replace('-', '_')
            model_name = f"dataset_{dataset_id}_chat_model"
            
            # Create chat model using Gemini engine
            prompt_template = f"""You are an AI assistant specialized in analyzing and discussing the dataset "{dataset_name}".

Dataset Information:
- Name: {dataset_name}
- Type: {dataset_type}
- Dataset ID: {dataset_id}

You are designed to help users understand and analyze this specific dataset. When answering questions:
1. Be specific about this dataset
2. Provide helpful insights when possible
3. Explain any patterns or concepts clearly
4. Suggest relevant analyses or questions
5. Be helpful and informative

User Question: {{{{question}}}}

Please provide a comprehensive answer about this dataset:"""

            # Create the chat model
            chat_model_result = self.create_gemini_model(
                model_name=model_name,
                model_type="chat",
                column_name="response"
            )
            
            # Update the model with specific prompt template if creation was successful
            if chat_model_result.get("status") == "created":
                try:
                    # Try to set a custom prompt template for this specific dataset
                    update_query = f"""
                    CREATE OR REPLACE MODEL {model_name}
                    PREDICT response
                    USING
                        engine = '{self.engine_name}',
                        model_name = '{self.default_model}',
                        prompt_template = '{prompt_template}',
                        max_tokens = 1500;
                    """
                    
                    self.connection.query(update_query)
                    logger.info(f"✅ Updated chat model {model_name} with dataset-specific prompt")
                    
                except Exception as update_error:
                    logger.warning(f"⚠️ Could not update model prompt template: {update_error}")
                    # Continue anyway - model was created successfully
            
            logger.info(f"✅ ML models created for dataset {dataset_id}")
            
            return {
                "success": True,
                "models_created": [
                    {
                        "name": model_name,
                        "type": "chat",
                        "engine": self.engine_name,
                        "status": chat_model_result.get("status", "unknown")
                    }
                ],
                "dataset_id": dataset_id,
                "dataset_name": dataset_name
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to create ML models for dataset {dataset_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "dataset_id": dataset_id
            }

    def delete_dataset_models(self, dataset_id: int) -> Dict[str, Any]:
        """Delete all MindsDB models associated with a dataset."""
        try:
            logger.info(f"🗑️ Deleting ML models for dataset {dataset_id}")
            
            # Ensure MindsDB connection
            if not self._ensure_connection():
                logger.error("❌ MindsDB connection failed")
                return {
                    "success": False,
                    "error": "MindsDB connection failed",
                    "dataset_id": dataset_id
                }
            
            deleted_models = []
            errors = []
            
            # List of model patterns to look for and delete
            model_patterns = [
                f"dataset_{dataset_id}_chat_model",
                f"dataset_{dataset_id}_model",
                f"dataset_{dataset_id}_embedding_model",
                f"dataset_{dataset_id}_vision_model"
            ]
            
            for model_name in model_patterns:
                try:
                    # Check if model exists
                    check_query = f"SHOW MODELS WHERE name = '{model_name}'"
                    result = self.connection.query(check_query)
                    
                    if result and hasattr(result, 'fetch'):
                        models_df = result.fetch()
                        if not models_df.empty:
                            # Model exists, delete it
                            logger.info(f"🗑️ Deleting model: {model_name}")
                            delete_query = f"DROP MODEL {model_name}"
                            self.connection.query(delete_query)
                            deleted_models.append(model_name)
                            logger.info(f"✅ Successfully deleted model: {model_name}")
                        else:
                            logger.info(f"ℹ️ Model {model_name} does not exist, skipping")
                    else:
                        logger.info(f"ℹ️ Could not check existence of model {model_name}, attempting delete anyway")
                        
                        # Try to delete anyway in case the check failed
                        try:
                            delete_query = f"DROP MODEL IF EXISTS {model_name}"
                            self.connection.query(delete_query)
                            deleted_models.append(model_name)
                            logger.info(f"✅ Successfully deleted model: {model_name}")
                        except Exception as delete_error:
                            error_msg = str(delete_error)
                            if "does not exist" not in error_msg.lower():
                                logger.warning(f"⚠️ Could not delete model {model_name}: {error_msg}")
                                errors.append(f"{model_name}: {error_msg}")
                            else:
                                logger.info(f"ℹ️ Model {model_name} does not exist")
                        
                except Exception as e:
                    error_msg = str(e)
                    if "does not exist" not in error_msg.lower():
                        logger.warning(f"⚠️ Error checking/deleting model {model_name}: {error_msg}")
                        errors.append(f"{model_name}: {error_msg}")
                    else:
                        logger.info(f"ℹ️ Model {model_name} does not exist")
            
            # Also clean up any other models that might follow different naming patterns
            try:
                # Get all models and find any that contain the dataset ID
                all_models_query = "SHOW MODELS"
                result = self.connection.query(all_models_query)
                
                if result and hasattr(result, 'fetch'):
                    all_models_df = result.fetch()
                    
                    # Look for models that contain the dataset ID
                    dataset_models = all_models_df[
                        all_models_df['NAME'].str.contains(f"dataset_{dataset_id}", case=False, na=False) |
                        all_models_df['NAME'].str.contains(f"_{dataset_id}_", case=False, na=False)
                    ]
                    
                    for _, model_row in dataset_models.iterrows():
                        model_name = model_row['NAME']
                        if model_name not in deleted_models:
                            try:
                                logger.info(f"🗑️ Deleting additional dataset model: {model_name}")
                                delete_query = f"DROP MODEL {model_name}"
                                self.connection.query(delete_query)
                                deleted_models.append(model_name)
                                logger.info(f"✅ Successfully deleted additional model: {model_name}")
                            except Exception as delete_error:
                                error_msg = str(delete_error)
                                logger.warning(f"⚠️ Could not delete additional model {model_name}: {error_msg}")
                                errors.append(f"{model_name}: {error_msg}")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not check for additional dataset models: {e}")
                errors.append(f"Additional model check failed: {str(e)}")
            
            result = {
                "success": len(deleted_models) > 0 or len(errors) == 0,
                "deleted_models": deleted_models,
                "errors": errors,
                "dataset_id": dataset_id
            }
            
            if deleted_models:
                logger.info(f"✅ Successfully deleted {len(deleted_models)} models for dataset {dataset_id}: {deleted_models}")
            else:
                logger.info(f"ℹ️ No models found to delete for dataset {dataset_id}")
                
            if errors:
                logger.warning(f"⚠️ Some errors occurred while deleting models for dataset {dataset_id}: {errors}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to delete models for dataset {dataset_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "dataset_id": dataset_id,
                "deleted_models": [],
                "errors": [str(e)]
            }

    # MindsDB supported file extensions
    SUPPORTED_FILE_EXTENSIONS = {
        '.csv': 'csv',
        '.xlsx': 'xlsx', 
        '.xls': 'xls',
        '.json': 'json',
        '.txt': 'txt',
        '.pdf': 'pdf',
        '.parquet': 'parquet'
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

    def create_model_for_uploaded_file(self, file_name: str, file_type: str) -> Optional[str]:
        """Create appropriate MindsDB model based on file type."""
        
        try:
            if not self._ensure_connection():
                logger.error("Could not connect to MindsDB")
                return None
            
            logger.info("✅ Connected to MindsDB")
            
            # Test file access
            test_query = f"SELECT * FROM files.{file_name} LIMIT 1"
            logger.info(f"🔍 Testing file access: {test_query}")
            
            try:
                result = self.connection.query(test_query)
                logger.info("✅ File is accessible in MindsDB")
            except Exception as e:
                logger.error(f"❌ Cannot access file in MindsDB: {e}")
                return None
            
            model_name = f"{file_name}_model"
            
            # Create different models based on file type
            if file_type in ['pdf', 'txt']:
                # RAG model for text-based files
                model_sql = f"""
                CREATE MODEL mindsdb.{model_name}
                FROM files 
                    (SELECT * FROM {file_name})
                PREDICT answer
                USING
                   engine="rag",
                   llm_type="openai",
                   input_column='question';
                """
                model_type = "RAG"
                
            elif file_type in ['csv', 'xlsx', 'xls', 'json', 'parquet']:
                # Knowledge base for structured data
                model_sql = f"""
                CREATE KNOWLEDGE_BASE mindsdb.{model_name}
                FROM files.{file_name}
                USING
                   model='text-embedding-ada-002',
                   storage=mindsdb;
                """
                model_type = "Knowledge Base"
            
            else:
                logger.error(f"Unsupported file type for model creation: {file_type}")
                return None
            
            logger.info(f"🤖 Creating {model_type} model: {model_name}")
            logger.info(f"SQL: {model_sql}")
            
            result = self.connection.query(model_sql)
            logger.info(f"✅ {model_type} model created successfully: {model_name}")
            
            return model_name
            
        except Exception as e:
            logger.error(f"❌ Error creating model: {e}")
            import traceback
            traceback.print_exc()
            return None

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
    
    def _load_dataset_for_visualization(self, dataset, db) -> Optional[pd.DataFrame]:
        """Load dataset data into a DataFrame for visualization"""
        try:
            # Check if dataset has files
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
                    # Try to construct file path from source_url
                    import os
                    possible_paths = [
                        f"storage/{dataset.source_url}",
                        f"../storage/{dataset.source_url}",
                        dataset.source_url
                    ]
                    for path in possible_paths:
                        if os.path.exists(path):
                            file_path = path
                            break
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"File not found for dataset {dataset.id}: {file_path}")
                return None
            
            # Load file based on type
            file_extension = file_path.split('.')[-1].lower()
            
            if file_extension == 'csv':
                df = pd.read_csv(file_path)
            elif file_extension in ['xlsx', 'xls']:
                df = pd.read_excel(file_path)
            elif file_extension == 'json':
                df = pd.read_json(file_path)
            elif file_extension == 'parquet':
                df = pd.read_parquet(file_path)
            else:
                logger.warning(f"Unsupported file type for visualization: {file_extension}")
                return None
            
            # Limit rows for performance
            if len(df) > 10000:
                logger.info(f"Dataset has {len(df)} rows, sampling 10000 for visualization")
                df = df.sample(n=10000, random_state=42)
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading dataset for visualization: {e}")
            return None

    # ============================================================
    # AGENT-BASED ARCHITECTURE METHODS (New)
    # ============================================================

    def get_model_config(self, dataset=None) -> Dict[str, Any]:
        """
        Get model configuration with optional dataset-specific overrides.
        Supports hybrid approach: global defaults with per-dataset customization.
        """
        try:
            # Default provider configuration
            default_provider = getattr(settings, 'DEFAULT_LLM_PROVIDER', 'google')

            # Check if dataset has custom model preference
            if dataset and hasattr(dataset, 'chat_model_name') and dataset.chat_model_name:
                provider = dataset.chat_model_provider or default_provider
                return {
                    'provider': provider,
                    'model_name': dataset.chat_model_name,
                    'api_key': self.api_key
                }

            # Use default configuration
            return {
                'provider': default_provider,
                'model_name': self.default_model,
                'api_key': self.api_key
            }
        except Exception as e:
            logger.error(f"Error getting model config: {e}")
            return {
                'provider': 'google',
                'model_name': self.default_model,
                'api_key': self.api_key
            }

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

            # Create new agent using MindsDB's pre-configured LLM
            # Don't pass model config - let MindsDB use its default configured LLM (OpenAI-based)
            logger.info(f"🤖 Creating agent '{agent_name}' with {len(tables)} tables")
            logger.info(f"📡 Using MindsDB's pre-configured LLM (OpenAI-based URL)")
            logger.debug(f"Agent tables: {tables}")

            agent = self.connection.agents.create(
                name=agent_name,
                data={'tables': tables},
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

            # Get file upload record
            from app.models.file_handler import FileUpload
            file_upload = db.query(FileUpload).filter(
                FileUpload.dataset_id == dataset.id
            ).first()

            if not file_upload:
                return {
                    "success": False,
                    "error": "No file upload found for dataset"
                }

            # Ensure file has MindsDB database connector
            connector_result = self.create_file_database_connector(file_upload)
            if not connector_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to create database connector: {connector_result.get('error')}"
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

    def chat_with_dataset_agent(self, dataset_id: int, message: str, db,
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

            # Setup appropriate agent based on dataset type
            if dataset.is_multi_file_dataset:
                agent_result = self.setup_multi_file_agent(dataset, db)
            else:
                agent_result = self.setup_single_file_agent(dataset, db)

            if not agent_result.get("success"):
                logger.warning(f"Agent setup failed: {agent_result.get('error')}, using fallback")
                return self._fallback_gemini_chat(message, dataset)

            agent_name = agent_result["agent_name"]

            # Get agent from MindsDB
            if not self._ensure_connection():
                logger.warning("Connection failed, using fallback")
                return self._fallback_gemini_chat(message, dataset)

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

                    for chunk in completion:
                        full_response += chunk

                    response_time = time.time() - start_time

                    logger.info(f"✅ Agent response complete in {response_time:.2f}s")

                    return {
                        "success": True,
                        "answer": full_response,
                        "source": "agent",
                        "agent_name": agent_name,
                        "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                        "tables_count": agent_result.get("tables_count", 1),
                        "response_time": response_time,
                        "streaming": True,
                        "model": self.get_model_config(dataset).get("model_name")
                    }

                except Exception as e:
                    logger.error(f"Streaming failed: {e}, trying non-streaming")
                    # Fall through to non-streaming

            # Non-streaming fallback
            try:
                completion = agent.completion(conversation)
                answer = completion.get('answer', '') if isinstance(completion, dict) else str(completion)

                response_time = time.time() - start_time

                return {
                    "success": True,
                    "answer": answer,
                    "source": "agent",
                    "agent_name": agent_name,
                    "dataset_type": "multi_file" if dataset.is_multi_file_dataset else "single_file",
                    "response_time": response_time,
                    "streaming": False
                }

            except Exception as e:
                logger.error(f"Agent query failed: {e}")
                return self._fallback_gemini_chat(message, dataset)

        except Exception as e:
            logger.error(f"❌ Chat with agent failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Fallback to direct Gemini API
            return self._fallback_gemini_chat(message, dataset)

    def _fallback_gemini_chat(self, message: str, dataset) -> Dict[str, Any]:
        """
        Fallback to direct Gemini API if agent-based approach fails.
        Maintains compatibility while agent system is being deployed.
        """
        try:
            logger.info("🔄 Using fallback Gemini API")

            # Build context from dataset
            context = f"""Dataset: {dataset.name}
Description: {dataset.description or 'No description'}
Type: {dataset.type.value if hasattr(dataset.type, 'value') else str(dataset.type)}

User Question: {message}

Please provide a helpful response based on the dataset information available."""

            # Use direct Gemini API
            model = genai.GenerativeModel(self.default_model)
            response = model.generate_content(context)

            return {
                "success": True,
                "answer": response.text,
                "source": "fallback_gemini",
                "streaming": False,
                "model": self.default_model
            }

        except Exception as e:
            logger.error(f"Fallback also failed: {e}")
            return {
                "success": False,
                "error": f"Unable to process request: {str(e)}"
            }


# Create service instance
mindsdb_service = MindsDBService()