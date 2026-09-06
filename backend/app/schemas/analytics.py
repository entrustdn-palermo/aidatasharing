from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class UsageStatsSummary(BaseModel):
    """Schema for aggregated usage statistics"""
    total_accesses: int = 0
    total_downloads: int = 0
    total_chats: int = 0
    total_api_calls: int = 0
    total_shares: int = 0
    unique_users: int = 0


class DailyActivity(BaseModel):
    """Schema for daily activity data"""
    date: str
    count: int


class TopDataset(BaseModel):
    """Schema for top dataset information"""
    dataset_id: int
    name: str
    access_count: int


class TopUser(BaseModel):
    """Schema for top user information"""
    user_id: int
    username: str
    access_count: int


class AnalyticsPeriod(BaseModel):
    """Schema for analytics time period"""
    start_date: str
    end_date: str


class DatasetAnalyticsResponse(BaseModel):
    """Schema for dataset analytics response"""
    dataset_id: int
    period: AnalyticsPeriod
    summary: UsageStatsSummary
    access_by_type: Dict[str, int]
    daily_activity: List[DailyActivity]


class OrganizationAnalyticsResponse(BaseModel):
    """Schema for organization analytics response"""
    organization_id: int
    period: AnalyticsPeriod
    summary: UsageStatsSummary
    top_datasets: List[TopDataset]
    top_users: List[TopUser]


class SystemMetric(BaseModel):
    """Schema for system metric entry"""
    timestamp: str
    cpu_usage_percent: Optional[float] = None
    memory_usage_percent: Optional[float] = None
    disk_usage_percent: Optional[float] = None
    total_datasets: Optional[int] = None
    total_users: Optional[int] = None
    total_organizations: Optional[int] = None
    mindsdb_health: Optional[str] = None


class SystemMetricsResponse(BaseModel):
    """Schema for system metrics response"""
    metrics: List[SystemMetric]
    period_hours: int
    total_records: int


class UsageStatsResponse(BaseModel):
    """Schema for usage statistics response"""
    date: str
    period_type: str
    dataset_id: Optional[int] = None
    organization_id: Optional[int] = None
    stats: UsageStatsSummary
    performance_metrics: Dict[str, float] = {}
