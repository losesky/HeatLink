from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class SourceTestResult(BaseModel):
    """Schema for a single source test result"""
    source_type: str
    success: bool
    error: Optional[str] = None
    items_count: int = 0
    elapsed_time: float = 0


class SourceTestRequest(BaseModel):
    """Schema for source test request"""
    source_type: str
    timeout: int = 60


class SuccessfulSourceResult(BaseModel):
    """Schema for a successful source test result"""
    source_type: str
    items_count: int
    elapsed_time: float


class FailedSourceResult(BaseModel):
    """Schema for a failed source test result"""
    source_type: str
    error: str


class TestSummary(BaseModel):
    """Schema for test summary"""
    total_sources: int
    successful_sources: int
    failed_sources: int
    success_rate: str
    total_time: str


class AllSourcesTestResult(BaseModel):
    """Schema for all sources test result"""
    summary: TestSummary
    successful_sources: List[SuccessfulSourceResult]
    failed_sources: List[FailedSourceResult]


class AllSourcesTestRequest(BaseModel):
    """Schema for all sources test request"""
    timeout: int = 60
    max_concurrent: int = 5 