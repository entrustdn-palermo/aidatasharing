"""
Entrust Data Sharing MCP Platform - Chat Agent Service

Handles agent-based chat interactions with datasets via MindsDB agents.
Extracted from MindsDBService for focused responsibility.
"""

import logging
import time
from typing import Dict, List, Optional, Any

import pandas as pd

logger = logging.getLogger(__name__)


def clean_agent_answer(answer: str) -> str:
    """Clean and extract the meaningful answer from an agent response."""
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


def build_dataset_summary_answer(dataset, message: str, dataset_df: pd.DataFrame,
                                  data_analysis: Dict[str, Any]) -> str:
    """Build a natural-language answer from dataset analysis data."""
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


class ChatAgentService:
    """Service handling agent-based chat interactions with datasets.

    Depends on a MindsDBService instance for connection, agent setup,
    and dataset access.
    """

    def __init__(self, mindsdb_service, agent_model: str):
        self._mindsdb = mindsdb_service
        self.agent_model = agent_model

    @property
    def connection(self):
        return self._mindsdb.connection

    async def chat_with_dataset_agent(
        self,
        dataset_id: int,
        message: str,
        db,
        session_id: str = None,
        stream: bool = True,
    ) -> Dict[str, Any]:
        """Chat with dataset using agent-based architecture.

        This is the main entry point replacing the old model-based chat.

        Features:
        - Persistent agents (no recreation overhead)
        - Multi-file support (cross-file analysis)
        - Streaming responses
        - Automatic fallback to direct API
        """
        start_time = time.time()

        try:
            # Get dataset
            from app.models.dataset import Dataset
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()

            if not dataset:
                return {"success": False, "error": "Dataset not found"}

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
                    dataset_df = await self._mindsdb.load_dataset_for_visualization(dataset, db)

                    if dataset_df is not None and not dataset_df.empty:
                        logger.info(f"✅ Loaded {len(dataset_df)} rows for visualization")

                        # Generate visualizations using LIDA
                        from app.services.data_visualization import get_visualization_service
                        viz_service = get_visualization_service(self._mindsdb.api_key)

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
                agent_result = self._mindsdb.setup_multi_file_agent(dataset, db)
            else:
                agent_result = self._mindsdb.setup_single_file_agent(dataset, db)

            if not agent_result.get("success"):
                error_msg = f"Agent setup failed: {agent_result.get('error')}"
                logger.error(error_msg)
                fallback_response = await self._chat_with_dataset_summary_fallback(
                    dataset=dataset,
                    message=message,
                    db=db,
                    start_time=start_time,
                    visualizations=visualizations,
                    data_analysis=data_analysis,
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
            if not self._mindsdb.ensure_connection():
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
                    final_answer = clean_agent_answer(last_answer if last_answer else full_response)

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
                        "model": self.agent_model,
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
                answer = clean_agent_answer(answer)

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

    async def _chat_with_dataset_summary_fallback(
        self,
        dataset,
        message: str,
        db,
        start_time: float,
        visualizations: Optional[List[Dict[str, Any]]] = None,
        data_analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fallback chat using dataset summary when agent setup fails."""
        try:
            dataset_df = await self._mindsdb.load_dataset_for_visualization(dataset, db)
            if dataset_df is None or dataset_df.empty:
                return {"success": False, "error": "Dataset data could not be loaded for fallback chat"}

            from app.services.data_visualization import get_visualization_service, sanitize_visualization_payload

            visualizations = visualizations or []
            data_analysis = data_analysis or {}
            if not data_analysis:
                viz_service = get_visualization_service(self._mindsdb.api_key)
                data_analysis = viz_service.analyze_dataset(dataset_df, dataset.name)
                data_analysis = sanitize_visualization_payload(data_analysis)

            answer = build_dataset_summary_answer(dataset, message, dataset_df, data_analysis)
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
