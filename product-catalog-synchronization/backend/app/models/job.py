"""Job and synchronization models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class JobStatus(str, Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    NORMALIZING = "NORMALIZING"
    MATCHING = "MATCHING"
    RECONCILING = "RECONCILING"
    GENERATING_OUTPUTS = "GENERATING_OUTPUTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SyncJob(BaseModel):
    """Represents a synchronization / reconciliation job."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0  # 0-100
    message: str = ""
    supplier_name: Optional[str] = None
    supplier_file: Optional[str] = None
    woobe_file: Optional[str] = None
    column_mapping: dict[str, str] = Field(default_factory=dict)
    matching_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    stats: Optional[dict[str, Any]] = None
    output_files: list[str] = Field(default_factory=list)
