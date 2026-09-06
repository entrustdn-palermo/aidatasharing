from fastapi import APIRouter, Depends, HTTPException, Request, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import json

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.organization import Organization
from app.models.dataset import Dataset
from app.models.analytics import (
    ActivityLog, UsageMetric, DatashareStats, UserSessionLog, ModelPerformanceLog,
    DatasetAccess, DatasetDownload, ChatInteraction, 
    APIUsage, UsageStats, SystemMetrics
)
from app.services.analytics import analytics_service
from app.schemas.analytics import (
    DatasetAnalyticsResponse, OrganizationAnalyticsResponse,
    UsageStatsResponse, SystemMetricsResponse
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Analytics Response Models
class OrganizationStatsResponse(BaseModel):
    id: int
    name: str
    total_users: int
    total_datasets: int
    total_models: int
    storage_used: float  # GB
    storage_limit: float  # GB

class UsageStatsResponse(BaseModel):
    total_api_calls: int
    total_predictions: int
    average_response_time: float  # ms
    uptime: float  # percentage

class TrendDataPoint(BaseModel):
    date: str
    count: int
    active_users: Optional[int] = None

class TrendsResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    dataset_uploads: List[TrendDataPoint]
    model_creations: List[TrendDataPoint]
    predictions: List[TrendDataPoint]
    user_activity: List[TrendDataPoint]

class ModelPerformanceResponse(BaseModel):
    id: str
    name: str
    accuracy: float
    predictions: int
    last_updated: str
    status: str

class UserActivityResponse(BaseModel):
    user_id: int
    name: str
    last_active: str
    actions_today: int
    role: str
    department: str

class DatasetUsageResponse(BaseModel):
    id: int
    name: str
    access_count: int
    last_accessed: str
    sharing_level: str

class StorageByDepartmentResponse(BaseModel):
    department: str
    storage: float
    percentage: float

class DataUsageResponse(BaseModel):
    most_accessed_datasets: List[DatasetUsageResponse]
    storage_by_department: List[StorageByDepartmentResponse]

class CostCategoryResponse(BaseModel):
    category: str
    amount: float
    percentage: float

class CostAnalysisResponse(BaseModel):
    total_cost: float
    cost_by_category: List[CostCategoryResponse]
    projected_monthly_cost: float

class AnalyticsResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    organization: OrganizationStatsResponse
    usage: UsageStatsResponse
    trends: TrendsResponse
    model_performance: List[ModelPerformanceResponse]
    user_activity: List[UserActivityResponse]
    data_usage: DataUsageResponse
    costs: CostAnalysisResponse

@router.get("/organization", response_model=AnalyticsResponse)
async def get_organization_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive analytics data for the user's organization
    """
    if not current_user.organization_id:
        # Return mock data for users without organizations
        return AnalyticsResponse(
            organization=OrganizationStatsResponse(
                id=0,
                name="Demo Organization",
                total_users=1,
                total_datasets=0,
                total_models=0,
                storage_used=0.0,
                storage_limit=100.0
            ),
            usage=UsageStatsResponse(
                total_api_calls=0,
                total_predictions=0,
                average_response_time=0.0,
                uptime=100.0
            ),
            trends=TrendsResponse(
                dataset_uploads=[],
                model_creations=[],
                predictions=[],
                user_activity=[]
            ),
            model_performance=[],
            user_activity=[],
            data_usage=DataUsageResponse(
                most_accessed_datasets=[],
                storage_by_department=[]
            ),
            costs=CostAnalysisResponse(
                total_cost=0.0,
                cost_by_category=[],
                projected_monthly_cost=0.0
            )
        )
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    organization = db.query(Organization).filter(
        Organization.id == current_user.organization_id
    ).first()
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Organization Statistics
    org_users_count = db.query(User).filter(
        User.organization_id == current_user.organization_id
    ).count()
    
    org_datasets_count = db.query(Dataset).filter(
        Dataset.organization_id == current_user.organization_id
    ).count()
    
    # Calculate total storage used (mock calculation)
    total_storage_used = db.query(func.sum(Dataset.size_bytes)).filter(
        Dataset.organization_id == current_user.organization_id
    ).scalar() or 0.0
    total_storage_used = total_storage_used / (1024**3)  # Convert to GB
    
    org_stats = OrganizationStatsResponse(
        id=organization.id,
        name=organization.name,
        total_users=org_users_count,
        total_datasets=org_datasets_count,
        total_models=15,  # Mock data - replace with actual model count
        storage_used=round(total_storage_used, 2),
        storage_limit=500.0  # Mock limit
    )
    
    # Usage Statistics
    total_api_calls = db.query(func.sum(APIUsage.calls)).filter(
        APIUsage.organization_id == current_user.organization_id,
        APIUsage.timestamp.between(start_dt, end_dt)
    ).scalar() or 0

    total_predictions = db.query(func.sum(ModelPerformanceLog.predictions)).filter(
        ModelPerformanceLog.organization_id == current_user.organization_id,
        ModelPerformanceLog.timestamp.between(start_dt, end_dt)
    ).scalar() or 0

    avg_response_time = db.query(func.avg(ModelPerformanceLog.response_time)).filter(
        ModelPerformanceLog.organization_id == current_user.organization_id,
        ModelPerformanceLog.timestamp.between(start_dt, end_dt)
    ).scalar() or 0.0

    # Uptime calculation (example: percentage of successful operations)
    total_operations = total_api_calls + total_predictions
    successful_operations = db.query(func.count(ModelPerformanceLog.id)).filter(
        ModelPerformanceLog.organization_id == current_user.organization_id,
        ModelPerformanceLog.timestamp.between(start_dt, end_dt),
        ModelPerformanceLog.status == 'success'
    ).scalar() or 0
    uptime = (successful_operations / total_operations * 100) if total_operations > 0 else 100.0

    usage_stats = UsageStatsResponse(
        total_api_calls=total_api_calls,
        total_predictions=total_predictions,
        average_response_time=avg_response_time,
        uptime=uptime
    )
    
    # Trends Data
    trends_data = get_trends_data(db, current_user.organization_id, start_dt, end_dt)
    
    # Model Performance (mock data)
    model_performance = [
        ModelPerformanceResponse(
            id="model_001",
            name="Customer Churn Prediction",
            accuracy=0.924,
            predictions=15847,
            last_updated="2024-01-15T14:22:00Z",
            status="excellent"
        ),
        ModelPerformanceResponse(
            id="model_002",
            name="Sales Forecasting",
            accuracy=0.887,
            predictions=8932,
            last_updated="2024-01-14T09:15:00Z",
            status="good"
        ),
        ModelPerformanceResponse(
            id="model_003",
            name="Demand Prediction",
            accuracy=0.756,
            predictions=3421,
            last_updated="2024-01-12T16:45:00Z",
            status="needs_attention"
        )
    ]
    
    # User Activity
    user_activity_data = get_user_activity(db, current_user.organization_id, start_dt, end_dt)
    
    # Data Usage
    data_usage = get_data_usage_stats(db, current_user.organization_id)
    
    # Cost Analysis (mock data)
    cost_analysis = CostAnalysisResponse(
        total_cost=2847.50,
        cost_by_category=[
            CostCategoryResponse(category="Storage", amount=1245.30, percentage=43.7),
            CostCategoryResponse(category="API Calls", amount=892.15, percentage=31.3),
            CostCategoryResponse(category="Model Training", amount=456.78, percentage=16.0),
            CostCategoryResponse(category="Data Processing", amount=253.27, percentage=8.9)
        ],
        projected_monthly_cost=8542.50
    )
    
    return AnalyticsResponse(
        organization=org_stats,
        usage=usage_stats,
        trends=trends_data,
        model_performance=model_performance,
        user_activity=user_activity_data,
        data_usage=data_usage,
        costs=cost_analysis
    )

def get_trends_data(db: Session, organization_id: int, start_date: datetime, end_date: datetime) -> TrendsResponse:
    """Generate trends data for the specified date range"""
    
    # Dataset uploads trend
    dataset_uploads_query = db.query(
        func.date(Dataset.created_at),
        func.count(Dataset.id)
    ).filter(
        Dataset.organization_id == organization_id,
        Dataset.created_at.between(start_date, end_date)
    ).group_by(func.date(Dataset.created_at)).all()

    dataset_uploads = [TrendDataPoint(date=str(date), count=count) for date, count in dataset_uploads_query]

    # Model creations trend (using ModelPerformanceLog as proxy)
    model_creations_query = db.query(
        func.date(ModelPerformanceLog.timestamp),
        func.count(ModelPerformanceLog.id)
    ).filter(
        ModelPerformanceLog.organization_id == organization_id,
        ModelPerformanceLog.timestamp.between(start_date, end_date)
    ).group_by(func.date(ModelPerformanceLog.timestamp)).all()

    model_creations = [TrendDataPoint(date=str(date), count=count) for date, count in model_creations_query]

    # Predictions trend
    predictions_query = db.query(
        func.date(ModelPerformanceLog.timestamp),
        func.sum(ModelPerformanceLog.predictions)
    ).filter(
        ModelPerformanceLog.organization_id == organization_id,
        ModelPerformanceLog.timestamp.between(start_date, end_date)
    ).group_by(func.date(ModelPerformanceLog.timestamp)).all()

    predictions = [TrendDataPoint(date=str(date), count=count or 0) for date, count in predictions_query]

    # User activity trend
    user_activity_query = db.query(
        func.date(UserSessionLog.login_time),
        func.count(func.distinct(UserSessionLog.user_id))
    ).filter(
        UserSessionLog.organization_id == organization_id,
        UserSessionLog.login_time.between(start_date, end_date)
    ).group_by(func.date(UserSessionLog.login_time)).all()

    user_activity = [TrendDataPoint(date=str(date), active_users=count) for date, count in user_activity_query]
    
    # Generate daily data points for the date range
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Mock data generation - replace with actual queries
        dataset_uploads.append(TrendDataPoint(
            date=date_str,
            count=max(1, int((current_date.timestamp() % 25)))
        ))
        
        model_creations.append(TrendDataPoint(
            date=date_str,
            count=max(1, int((current_date.timestamp() % 7)))
        ))
        
        predictions.append(TrendDataPoint(
            date=date_str,
            count=max(100, int((current_date.timestamp() % 2000)))
        ))
        
        user_activity.append(TrendDataPoint(
            date=date_str,
            count=0,  # Not used for user activity
            active_users=max(10, int((current_date.timestamp() % 100)))
        ))
        
        current_date += timedelta(days=1)
    
    return TrendsResponse(
        dataset_uploads=dataset_uploads[-7:],  # Last 7 days
        model_creations=model_creations[-7:],
        predictions=predictions[-7:],
        user_activity=user_activity[-7:]
    )

def get_user_activity(db: Session, organization_id: int, start_date: datetime, end_date: datetime) -> List[UserActivityResponse]:
    today = datetime.now().date()
    last_activity_summary = db.query(
        ActivityLog.user_id.label('user_id'),
        func.max(ActivityLog.created_at).label('last_active')
    ).filter(
        ActivityLog.organization_id == organization_id,
        ActivityLog.created_at.between(start_date, end_date)
    ).group_by(ActivityLog.user_id).subquery()

    today_activity_summary = db.query(
        ActivityLog.user_id.label('user_id'),
        func.count(ActivityLog.id).label('actions_today')
    ).filter(
        ActivityLog.organization_id == organization_id,
        func.date(ActivityLog.created_at) == today
    ).group_by(ActivityLog.user_id).subquery()

    rows = db.query(
        User,
        last_activity_summary.c.last_active,
        today_activity_summary.c.actions_today
    ).outerjoin(
        last_activity_summary,
        last_activity_summary.c.user_id == User.id
    ).outerjoin(
        today_activity_summary,
        today_activity_summary.c.user_id == User.id
    ).filter(
        User.organization_id == organization_id
    ).all()

    return [
        UserActivityResponse(
            user_id=user.id,
            name=user.full_name or user.email.split('@')[0],
            last_active=last_active.isoformat() if last_active else None,
            actions_today=actions_today or 0,
            role=user.role or 'User',
            department='General'
        ) for user, last_active, actions_today in rows
    ]

def get_data_usage_stats(db: Session, organization_id: int) -> DataUsageResponse:
    """Get data usage statistics for the organization"""
    
    # Most accessed datasets
    most_accessed_query = db.query(
        Dataset,
        func.count(DatasetAccess.id).label('access_count'),
        func.max(DatasetAccess.timestamp).label('last_accessed')
    ).outerjoin(DatasetAccess).filter(
        Dataset.organization_id == organization_id,
        Dataset.is_deleted == False,
        Dataset.is_active == True
    ).group_by(Dataset.id).order_by(desc('access_count')).limit(5).all()

    most_accessed = [
        DatasetUsageResponse(
            id=dataset.id,
            name=dataset.name,
            access_count=access_count,
            last_accessed=last_accessed.isoformat() if last_accessed else None,
            sharing_level=dataset.sharing_level
        ) for dataset, access_count, last_accessed in most_accessed_query
    ]

    # Storage by department
    total_dataset_storage = db.query(func.sum(Dataset.size_bytes)).filter(
        Dataset.organization_id == organization_id,
        Dataset.is_deleted == False,
        Dataset.is_active == True
    ).scalar() or 0
    storage_by_dept_query = [('General', total_dataset_storage)]

    total_storage = sum(size or 0 for _, size in storage_by_dept_query) or 1
    storage_by_dept = [
        StorageByDepartmentResponse(
            department=dept or 'Unassigned',
            storage=(size or 0) / (1024**3),
            percentage=((size or 0) / total_storage * 100)
        ) for dept, size in storage_by_dept_query
    ]

    return DataUsageResponse(
        most_accessed_datasets=most_accessed,
        storage_by_department=storage_by_dept
    )

@router.get("/export")
async def export_analytics_report(
    format: str = Query("csv", description="Export format: csv, json, excel"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export analytics report in specified format
    """
    # Implementation for exporting analytics data
    # This would generate and return downloadable files
    
    return {
        "message": "Analytics report export initiated",
        "format": format,
        "start_date": start_date,
        "end_date": end_date,
        "download_url": f"/analytics/download/{format}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }

@router.post("/activity")
async def log_activity(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Log user activity for analytics tracking
    """
    
    activity_log = ActivityLog(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        timestamp=datetime.utcnow(),
        ip_address="0.0.0.0",  # Would be extracted from request
        user_agent="unknown"   # Would be extracted from request headers
    )
    
    db.add(activity_log)
    db.commit()
    
    return {"message": "Activity logged successfully"}

@router.get("/real-time")
async def get_real_time_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get real-time analytics metrics for dashboard widgets
    """
    
    if not current_user.organization_id:
        # Return demo data for users without organizations
        return {
            "active_users_now": 1,
            "api_calls_last_hour": 0,
            "predictions_last_hour": 0,
            "system_load": 0.1,
            "database_connections": 1,
            "cache_hit_rate": 100.0,
            "average_response_time": 50.0,
            "error_rate": 0.0,
            "timestamp": datetime.now().isoformat()
        }
    
    # Real-time metrics (mock data)
    return {
        "active_users_now": 23,
        "api_calls_last_hour": 1247,
        "predictions_last_hour": 543,
        "system_load": 67.8,
        "database_connections": 12,
        "cache_hit_rate": 94.2,
        "average_response_time": 156.7,
        "error_rate": 0.12,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/performance/{model_id}")
async def get_model_performance_details(
    model_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed performance metrics for a specific model
    """
    
    # Mock detailed model performance data
    return {
        "model_id": model_id,
        "accuracy_history": [
            {"date": "2024-01-10", "accuracy": 0.891},
            {"date": "2024-01-11", "accuracy": 0.898},
            {"date": "2024-01-12", "accuracy": 0.912},
            {"date": "2024-01-13", "accuracy": 0.924},
            {"date": "2024-01-14", "accuracy": 0.919},
            {"date": "2024-01-15", "accuracy": 0.924}
        ],
        "prediction_volume": [
            {"date": "2024-01-10", "count": 1250},
            {"date": "2024-01-11", "count": 1340},
            {"date": "2024-01-12", "count": 1567},
            {"date": "2024-01-13", "count": 1623},
            {"date": "2024-01-14", "count": 1489},
            {"date": "2024-01-15", "count": 1578}
        ],
        "response_times": [
            {"date": "2024-01-10", "avg_ms": 234},
            {"date": "2024-01-11", "avg_ms": 267},
            {"date": "2024-01-12", "avg_ms": 198},
            {"date": "2024-01-13", "avg_ms": 245},
            {"date": "2024-01-14", "avg_ms": 289},
            {"date": "2024-01-15", "avg_ms": 223}
        ],
        "error_rates": [
            {"date": "2024-01-10", "rate": 0.23},
            {"date": "2024-01-11", "rate": 0.18},
            {"date": "2024-01-12", "rate": 0.15},
            {"date": "2024-01-13", "rate": 0.12},
            {"date": "2024-01-14", "rate": 0.19},
            {"date": "2024-01-15", "rate": 0.14}
        ]
    }

@router.get("/user-activity")
async def get_user_activity_endpoint(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: Optional[int] = Query(None, description="Specific user ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user activity analytics"""
    if not current_user.organization_id:
        return []
    
    # Set default date range if not provided
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    return get_user_activity(db, current_user.organization_id, start_dt, end_dt)

@router.get("/dataset-usage")
async def get_dataset_usage_endpoint(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    dataset_id: Optional[int] = Query(None, description="Specific dataset ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dataset usage analytics"""
    if not current_user.organization_id:
        return {"most_accessed_datasets": [], "storage_by_department": []}
    
    return get_data_usage_stats(db, current_user.organization_id)

@router.get("/model-performance")
async def get_model_performance_endpoint(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    model_id: Optional[int] = Query(None, description="Specific model ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get model performance analytics"""
    if not current_user.organization_id:
        return []
    
    # Mock model performance data
    return [
        ModelPerformanceResponse(
            id="model_001",
            name="Customer Churn Prediction",
            accuracy=0.924,
            predictions=15847,
            last_updated="2024-01-15T14:22:00Z",
            status="excellent"
        ),
        ModelPerformanceResponse(
            id="model_002",
            name="Sales Forecasting",
            accuracy=0.887,
            predictions=8932,
            last_updated="2024-01-14T09:15:00Z",
            status="good"
        )
    ]

@router.post("/log/dataset-access")
async def log_dataset_access(
    dataset_id: int,
    access_type: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session_id: Optional[str] = None,
    access_method: str = "web",
    content_preview: Optional[str] = None,
    query_text: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Log dataset access event"""
    try:
        # Verify dataset exists and user has access
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Log the access in background
        background_tasks.add_task(
            analytics_service.log_dataset_access,
            dataset_id=dataset_id,
            access_type=access_type,
            user_id=user.id if user else None,
            session_id=session_id,
            request=request,
            access_method=access_method,
            content_preview=content_preview,
            query_text=query_text,
            organization_id=dataset.organization_id
        )
        
        return {"status": "logged", "dataset_id": dataset_id, "access_type": access_type}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging access: {str(e)}")

@router.post("/log/dataset-download")
async def log_dataset_download(
    dataset_id: int,
    file_format: str,
    download_method: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    file_size_bytes: Optional[int] = None,
    success: bool = True,
    share_token: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Log dataset download event"""
    try:
        # Verify dataset exists
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Log the download in background
        background_tasks.add_task(
            analytics_service.log_dataset_download,
            dataset_id=dataset_id,
            file_format=file_format,
            download_method=download_method,
            user_id=user.id if user else None,
            request=request,
            file_size_bytes=file_size_bytes,
            success=success,
            share_token=share_token,
            organization_id=dataset.organization_id
        )
        
        return {"status": "logged", "dataset_id": dataset_id, "download_method": download_method}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging download: {str(e)}")

@router.post("/log/chat-interaction")
async def log_chat_interaction(
    dataset_id: int,
    user_message: str,
    ai_response: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session_id: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    tokens_used: Optional[int] = None,
    response_time_seconds: Optional[float] = None,
    success: bool = True,
    db: Session = Depends(get_db)
):
    """Log AI chat interaction"""
    try:
        # Verify dataset exists
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Log the interaction in background
        background_tasks.add_task(
            analytics_service.log_chat_interaction,
            dataset_id=dataset_id,
            user_message=user_message,
            ai_response=ai_response,
            user_id=user.id if user else None,
            session_id=session_id,
            request=request,
            llm_provider=llm_provider,
            llm_model=llm_model,
            tokens_used=tokens_used,
            response_time_seconds=response_time_seconds,
            success=success,
            organization_id=dataset.organization_id
        )
        
        return {"status": "logged", "dataset_id": dataset_id, "interaction_logged": True}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging chat: {str(e)}")

@router.get("/dataset/{dataset_id}", response_model=DatasetAnalyticsResponse)
async def get_dataset_analytics(
    dataset_id: int,
    start_date: Optional[datetime] = Query(None, description="Start date for analytics (defaults to 30 days ago)"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics (defaults to now)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive analytics for a specific dataset"""
    try:
        # Verify dataset exists and user has access
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        # Check if user has access to this dataset
        if user.role != "admin" and dataset.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        analytics = await analytics_service.get_dataset_analytics(
            dataset_id=dataset_id,
            start_date=start_date,
            end_date=end_date,
            organization_id=user.organization_id if user.role != "admin" else None
        )
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting analytics: {str(e)}")

@router.get("/organization/{organization_id}", response_model=OrganizationAnalyticsResponse)
async def get_organization_analytics(
    organization_id: int,
    start_date: Optional[datetime] = Query(None, description="Start date for analytics"),
    end_date: Optional[datetime] = Query(None, description="End date for analytics"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive analytics for an organization"""
    try:
        # Check if user has access to this organization
        if user.role != "admin" and user.organization_id != organization_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Verify organization exists
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        analytics = await analytics_service.get_organization_analytics(
            organization_id=organization_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting organization analytics: {str(e)}")

@router.get("/dashboard/overview")
async def get_dashboard_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get overview analytics for dashboard"""
    try:
        # Get date ranges
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        
        # Base query filters
        base_filters = []
        if user.role != "admin":
            base_filters.append(DatasetAccess.organization_id == user.organization_id)
        
        # 24 hour metrics
        accesses_24h = db.query(DatasetAccess).filter(
            DatasetAccess.timestamp >= last_24h,
            *base_filters
        ).count()
        
        downloads_24h = db.query(DatasetDownload).filter(
            DatasetDownload.started_at >= last_24h,
            *([DatasetDownload.organization_id == user.organization_id] if user.role != "admin" else [])
        ).count()
        
        chats_24h = db.query(ChatInteraction).filter(
            ChatInteraction.timestamp >= last_24h,
            *([ChatInteraction.organization_id == user.organization_id] if user.role != "admin" else [])
        ).count()
        
        # 7 day metrics
        accesses_7d = db.query(DatasetAccess).filter(
            DatasetAccess.timestamp >= last_7d,
            *base_filters
        ).count()
        
        # Most active datasets (last 7 days)
        top_datasets_query = db.query(
            DatasetAccess.dataset_id,
            Dataset.name,
            func.count(DatasetAccess.id).label('access_count')
        ).join(Dataset).filter(
            DatasetAccess.timestamp >= last_7d,
            *base_filters
        ).group_by(DatasetAccess.dataset_id, Dataset.name).order_by(
            func.count(DatasetAccess.id).desc()
        ).limit(5)
        
        top_datasets = top_datasets_query.all()
        
        # Recent activity
        recent_activity = db.query(DatasetAccess).filter(
            *base_filters
        ).order_by(DatasetAccess.timestamp.desc()).limit(10).all()
        
        return {
            "last_24_hours": {
                "total_accesses": accesses_24h,
                "total_downloads": downloads_24h,
                "total_chats": chats_24h
            },
            "last_7_days": {
                "total_accesses": accesses_7d
            },
            "top_datasets": [
                {
                    "dataset_id": row.dataset_id,
                    "name": row.name,
                    "access_count": row.access_count
                }
                for row in top_datasets
            ],
            "recent_activity": [
                {
                    "access_id": activity.access_id,
                    "dataset_id": activity.dataset_id,
                    "access_type": activity.access_type,
                    "timestamp": activity.timestamp.isoformat(),
                    "user_id": activity.user_id
                }
                for activity in recent_activity
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dashboard overview: {str(e)}")

@router.get("/real-time/activity")
async def get_real_time_activity(
    user: User = Depends(get_current_user),
    limit: int = Query(20, description="Number of recent activities to return"),
    db: Session = Depends(get_db)
):
    """Get real-time activity feed"""
    try:
        # Base query filters
        base_filters = []
        if user.role != "admin":
            base_filters.append(DatasetAccess.organization_id == user.organization_id)
        
        # Get recent activities
        activities = db.query(DatasetAccess).filter(
            *base_filters
        ).order_by(DatasetAccess.timestamp.desc()).limit(limit).all()
        
        return {
            "activities": [
                {
                    "access_id": activity.access_id,
                    "dataset_id": activity.dataset_id,
                    "access_type": activity.access_type,
                    "timestamp": activity.timestamp.isoformat(),
                    "user_id": activity.user_id,
                    "ip_address": activity.ip_address,
                    "success": activity.success
                }
                for activity in activities
            ],
            "total_count": len(activities),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting real-time activity: {str(e)}")

@router.get("/system/metrics")
async def get_system_metrics(
    user: User = Depends(get_current_user),
    hours: int = Query(24, description="Number of hours of metrics to retrieve"),
    db: Session = Depends(get_db)
):
    """Get system performance metrics (admin only)"""
    try:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        metrics = db.query(SystemMetrics).filter(
            SystemMetrics.timestamp >= start_time
        ).order_by(SystemMetrics.timestamp.desc()).all()
        
        return {
            "metrics": [
                {
                    "timestamp": metric.timestamp.isoformat(),
                    "cpu_usage_percent": metric.cpu_usage_percent,
                    "memory_usage_percent": metric.memory_usage_percent,
                    "disk_usage_percent": metric.disk_usage_percent,
                    "total_datasets": metric.total_datasets,
                    "total_users": metric.total_users,
                    "total_organizations": metric.total_organizations,
                    "mindsdb_health": metric.mindsdb_health
                }
                for metric in metrics
            ],
            "period_hours": hours,
            "total_records": len(metrics)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system metrics: {str(e)}")

@router.post("/system/record-metrics")
async def record_system_metrics(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user)
):
    """Manually trigger system metrics recording (admin only)"""
    try:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        background_tasks.add_task(analytics_service.record_system_metrics)
        
        return {"status": "metrics_recording_scheduled"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scheduling metrics recording: {str(e)}")

@router.get("/export/dataset/{dataset_id}")
async def export_dataset_analytics(
    dataset_id: int,
    format: str = Query("json", description="Export format: json, csv"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export dataset analytics data"""
    try:
        # Verify dataset access
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        
        if user.role != "admin" and dataset.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get analytics data
        analytics = await analytics_service.get_dataset_analytics(
            dataset_id=dataset_id,
            start_date=start_date,
            end_date=end_date,
            organization_id=user.organization_id if user.role != "admin" else None
        )
        
        if format.lower() == "csv":
            # Convert to CSV format
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            writer.writerow(['metric', 'value'])
            
            # Write summary data
            for key, value in analytics.get('summary', {}).items():
                writer.writerow([key, value])
            
            csv_data = output.getvalue()
            output.close()
            
            return {"data": csv_data, "format": "csv"}
        
        return {"data": analytics, "format": "json"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting analytics: {str(e)}")