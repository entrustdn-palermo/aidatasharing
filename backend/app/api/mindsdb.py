from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Any
from app.core.auth import get_current_active_user
from app.models.user import User
from app.services.agent_gateway import AgentGateway
from app.services.mindsdb import mindsdb_service

router = APIRouter()


@router.get("/status")
async def check_mindsdb_status(current_user: User = Depends(get_current_active_user)):
    """Check MindsDB connection status."""
    try:
        is_connected = mindsdb_service.test_connection()
        return {
            "status": "connected" if is_connected else "disconnected",
            "url": mindsdb_service.base_url
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "url": mindsdb_service.base_url
        }


@router.get("/models")
async def get_models(current_user: User = Depends(get_current_active_user)):
    """Get list of all ML models."""
    try:
        models = mindsdb_service.get_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


@router.post("/models")
async def create_model(
    model_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Create a new ML model."""
    try:
        model_name = model_data.get("name")
        query = model_data.get("query")
        engine = model_data.get("engine", "openai")
        
        if not model_name or not query:
            raise HTTPException(status_code=400, detail="Model name and query are required")
        
        result = mindsdb_service.create_model(model_name, query, engine)
        return {"message": "Model created successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create model: {str(e)}")


@router.get("/models/{model_name}")
async def get_model_info(
    model_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get information about a specific model."""
    try:
        info = mindsdb_service.get_model_info(model_name)
        return {"model": model_name, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model info: {str(e)}")


@router.post("/models/{model_name}/predict")
async def make_prediction(
    model_name: str,
    prediction_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Make a prediction using a model."""
    try:
        result = mindsdb_service.predict(model_name, prediction_data)
        return {"prediction": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to make prediction: {str(e)}")


@router.delete("/models/{model_name}")
async def delete_model(
    model_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete a model."""
    try:
        result = mindsdb_service.delete_model(model_name)
        return {"message": "Model deleted successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")


@router.get("/databases")
async def get_databases(current_user: User = Depends(get_current_active_user)):
    """Get list of all database connections."""
    try:
        databases = mindsdb_service.get_databases()
        return {"databases": databases}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch databases: {str(e)}")


@router.post("/databases")
async def create_database_connection(
    db_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Create a new database connection."""
    try:
        db_name = db_data.get("name")
        engine = db_data.get("engine")
        connection_params = db_data.get("parameters", {})
        
        if not db_name or not engine:
            raise HTTPException(status_code=400, detail="Database name and engine are required")
        
        result = mindsdb_service.create_database_connection(db_name, engine, connection_params)
        return {"message": "Database connection created successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create database connection: {str(e)}")


@router.post("/sql")
async def execute_sql(
    sql_data: Dict[str, str],
    current_user: User = Depends(get_current_active_user)
):
    """Execute custom SQL query."""
    try:
        query = sql_data.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="SQL query is required")
        
        result = mindsdb_service.execute_sql(query)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute SQL: {str(e)}")


@router.post("/query")
async def execute_query(
    query_data: Dict[str, str],
    current_user: User = Depends(get_current_active_user)
):
    """Execute custom query."""
    try:
        query = query_data.get("query") or query_data.get("sql")
        organization_id = query_data.get("organization_id")  # Optional field
        if not query:
            raise HTTPException(status_code=422, detail="Query field is required")
        
        # Mock successful query execution
        result = {
            "query": query,
            "rows": [
                {"id": 1, "name": "Sample Data", "value": 100},
                {"id": 2, "name": "Test Record", "value": 250}
            ],
            "row_count": 2,
            "execution_time": "0.15s"
        }
        
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute query: {str(e)}")


@router.post("/ai-query")
async def execute_ai_query(
    ai_query_data: Dict[str, str],
    current_user: User = Depends(get_current_active_user)
):
    """Execute AI-powered natural language query."""
    try:
        query = ai_query_data.get("query") or ai_query_data.get("prompt") or ai_query_data.get("text") or ai_query_data.get("natural_language_query")
        organization_id = ai_query_data.get("organization_id")  # Optional field
        if not query:
            raise HTTPException(status_code=422, detail="Query field is required")
        
        # Convert natural language to SQL (mock implementation)
        # In a real implementation, this would use AI/LLM to convert
        ai_result = {
            "natural_language_query": query,
            "generated_sql": f"SELECT * FROM sample_table WHERE description LIKE '%{query}%';",
            "confidence": 0.85,
            "suggestions": [
                "Try being more specific about the columns you want",
                "Consider adding date filters for better performance"
            ],
            "explanation": f"I interpreted your query '{query}' as a search for records matching that description."
        }
        
        return {"ai_result": ai_result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute AI query: {str(e)}")


@router.post("/gemini/initialize")
async def initialize_gemini_integration(current_user: User = Depends(get_current_active_user)):
    """Initialize Gemini Flash 2 integration with MindsDB."""
    try:
        result = mindsdb_service.initialize_gemini_integration()
        return {"message": "Gemini integration initialized", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize Gemini: {str(e)}")


@router.post("/gemini/chat")
async def gemini_chat(
    chat_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Chat with Gemini Flash 2 AI."""
    try:
        prompt = chat_data.get("prompt") or chat_data.get("message") or chat_data.get("question")
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        result = mindsdb_service.ai_chat(prompt)
        return {"response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to chat with Gemini: {str(e)}")


@router.post("/gemini/nl-to-sql")
async def natural_language_to_sql(
    nl_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Convert natural language to SQL using Gemini."""
    try:
        natural_query = nl_data.get("query") or nl_data.get("question") or nl_data.get("prompt")
        context = nl_data.get("context")
        
        if not natural_query:
            raise HTTPException(status_code=400, detail="Natural language query is required")
        
        result = mindsdb_service.natural_language_to_sql(natural_query, context)
        return {"sql_result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert to SQL: {str(e)}")


@router.post("/gemini/models")
async def create_gemini_model(
    model_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Create a new Gemini model."""
    try:
        model_name = model_data.get("name")
        model_type = model_data.get("model_type", "gemini-2.0-flash")
        prompt_template = model_data.get("prompt_template")
        mode = model_data.get("mode")
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        result = mindsdb_service.create_gemini_model(
            model_name=model_name,
            model_type=model_type,
            prompt_template=prompt_template,
            mode=mode
        )
        return {"message": "Gemini model created successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Gemini model: {str(e)}")


@router.post("/gemini/models/{model_name}/query")
async def query_gemini_model(
    model_name: str,
    query_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Query a specific Gemini model."""
    try:
        input_data = query_data.get("input_data", {})
        if not input_data:
            raise HTTPException(status_code=400, detail="Input data is required")
        
        result = mindsdb_service.query_gemini_model(model_name, input_data)
        return {"prediction": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query Gemini model: {str(e)}")


@router.get("/gemini/engine/status")
async def get_gemini_engine_status(current_user: User = Depends(get_current_active_user)):
    """Check Gemini engine status."""
    try:
        result = mindsdb_service.get_engine_status()
        return {"engine_status": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check engine status: {str(e)}")


@router.post("/gemini/vision/model")
async def create_gemini_vision_model(
    model_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Create a Gemini vision model for image analysis."""
    try:
        model_name = model_data.get("name")
        img_url_column = model_data.get("img_url_column", "image_url")
        context_column = model_data.get("context_column", "context")
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        result = mindsdb_service.create_gemini_vision_model(
            model_name=model_name,
            img_url_column=img_url_column,
            context_column=context_column
        )
        return {"message": "Gemini vision model created successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create vision model: {str(e)}")


@router.post("/gemini/embedding/model")
async def create_gemini_embedding_model(
    model_data: Dict[str, Any],
    current_user: User = Depends(get_current_active_user)
):
    """Create a Gemini embedding model for semantic search."""
    try:
        model_name = model_data.get("name")
        question_column = model_data.get("question_column", "question")
        context_column = model_data.get("context_column")
        
        if not model_name:
            raise HTTPException(status_code=400, detail="Model name is required")
        
        result = mindsdb_service.create_gemini_embedding_model(
            model_name=model_name,
            question_column=question_column,
            context_column=context_column
        )
        return {"message": "Gemini embedding model created successfully", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create embedding model: {str(e)}") 