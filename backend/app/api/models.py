"""
/api/models — DB-backed model lifecycle (un-mocked).

Routes use ModelTrainingService to orchestrate MindsDB training, status
polling, prediction, and deletion through the DatasetModel table.

Error convention:
  ValueError("not found")  → 404
  ValueError("Access denied") → 403
  ValueError("Invalid target" / "not supported") → 400
  ValueError("not ready") → 409
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.model_training import ModelTrainingService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────


class ModelCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    dataset_id: int
    target_column: str
    name: Optional[str] = None


class ModelResponse(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}

    id: int
    dataset_id: int
    name: str
    model_type: str
    mindsdb_model_name: str
    target_column: Optional[str] = None
    feature_columns: Optional[List[str]] = None
    engine_type: Optional[str] = None
    status: str
    accuracy: Optional[str] = None
    training_time: Optional[int] = None
    prediction_count: int = 0
    error_message: Optional[str] = None
    is_active: bool = True
    is_deleted: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ModelStatusResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: int
    status: str
    accuracy: Optional[str] = None
    training_time: Optional[int] = None
    error_message: Optional[str] = None
    last_updated: Optional[str] = None


class PredictRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    input: Dict[str, Any]


class PredictResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: int
    predictions: List[Dict[str, Any]]


# ── Helper ────────────────────────────────────────────────────────────────


def _get_training_service(db: Session) -> ModelTrainingService:
    """Factory — kept as a plain function so tests can patch ModelTrainingService."""
    return ModelTrainingService(db)


def _handle_value_error(e: ValueError) -> HTTPException:
    msg = str(e)
    lower = msg.lower()
    if "not found" in lower:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "access denied" in lower:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
    if "not ready" in lower:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    # Invalid target, not supported, unsafe, etc.
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


def _model_to_response(m: Any) -> ModelResponse:
    return ModelResponse(
        id=m.id,
        dataset_id=m.dataset_id,
        name=m.name,
        model_type=m.model_type,
        mindsdb_model_name=m.mindsdb_model_name,
        target_column=m.target_column,
        feature_columns=m.feature_columns,
        engine_type=m.engine_type,
        status=m.status,
        accuracy=m.accuracy,
        training_time=m.training_time,
        prediction_count=m.prediction_count or 0,
        error_message=m.error_message,
        is_active=True if m.is_active is None else m.is_active,
        is_deleted=False if m.is_deleted is None else m.is_deleted,
        created_at=m.created_at.isoformat() if m.created_at else None,
        updated_at=m.updated_at.isoformat() if m.updated_at else None,
    )


def _model_to_status(m: Any) -> ModelStatusResponse:
    return ModelStatusResponse(
        id=m.id,
        status=m.status,
        accuracy=m.accuracy,
        training_time=m.training_time,
        error_message=m.error_message,
        last_updated=m.updated_at.isoformat() if m.updated_at else None,
    )


# ── Routes ────────────────────────────────────────────────────────────────


@router.get("/", response_model=List[ModelResponse])
async def list_models(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all non-deleted models the current user can access."""
    svc = _get_training_service(db)
    models = svc.list_models_for_user(current_user)
    return [_model_to_response(m) for m in models]


@router.post("/", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start training a new model.

    Returns immediately with ``status='training'``.  Poll
    ``GET /{id}/status`` for completion.
    """
    svc = _get_training_service(db)
    try:
        model = svc.train_model(
            dataset_id=body.dataset_id,
            user=current_user,
            target_column=body.target_column,
            name=body.name,
        )
    except ValueError as e:
        _handle_value_error(e)
    return _model_to_response(model)


@router.get("/{model_id:int}", response_model=ModelResponse)
async def get_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single model by id."""
    svc = _get_training_service(db)
    try:
        model = svc.get_model(model_id, current_user)
    except ValueError as e:
        _handle_value_error(e)
    return _model_to_response(model)


@router.get("/{model_id:int}/status", response_model=ModelStatusResponse)
async def get_model_status(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Refresh model status from MindsDB and return current state."""
    svc = _get_training_service(db)
    try:
        model = svc.get_model(model_id, current_user)
    except ValueError as e:
        _handle_value_error(e)

    # Refresh from MindsDB (no-op if already terminal)
    model = svc.refresh_status(model)
    db.refresh(model)
    return _model_to_status(model)


@router.post("/{model_id:int}/predict", response_model=PredictResponse)
async def predict(
    model_id: int,
    body: PredictRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run a prediction against a completed model."""
    svc = _get_training_service(db)
    try:
        model = svc.get_model(model_id, current_user)
    except ValueError as e:
        _handle_value_error(e)

    try:
        predictions = svc.predict(model, body.input)
    except ValueError as e:
        _handle_value_error(e)

    return PredictResponse(id=model_id, predictions=predictions)


@router.delete("/{model_id:int}")
async def delete_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete a model and drop it from MindsDB."""
    svc = _get_training_service(db)
    try:
        model = svc.get_model(model_id, current_user)
    except ValueError as e:
        _handle_value_error(e)

    svc.delete_model(model, current_user)
    return {"message": f"Model {model_id} deleted"}
