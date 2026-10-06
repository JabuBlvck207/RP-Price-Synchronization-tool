"""SQLAlchemy ORM models for persistent storage."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobStatusEnum(str, enum.Enum):
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


class UserRoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    jobs: Mapped[list["SyncJobRecord"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_org_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default=UserRoleEnum.OPERATOR.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    jobs: Mapped[list["SyncJobRecord"]] = relationship(back_populates="created_by_user")


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_org_supplier_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_column_mapping: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="suppliers")
    jobs: Mapped[list["SyncJobRecord"]] = relationship(back_populates="supplier")


class SyncJobRecord(Base):
    """Persistent record of a reconciliation / synchronization job."""

    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(30), default=JobStatusEnum.PENDING.value, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")

    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supplier_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    supplier_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    woobe_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    woobe_file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    column_mapping: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    matching_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_files: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Optional["Organization"]] = relationship(back_populates="jobs")
    supplier: Mapped[Optional["Supplier"]] = relationship(back_populates="jobs")
    created_by_user: Mapped[Optional["User"]] = relationship(back_populates="jobs")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class AuditLog(Base):
    """Audit trail for user and system actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sync_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    job: Mapped[Optional["SyncJobRecord"]] = relationship(back_populates="audit_logs")


class WooStore(Base):
    """WooCommerce store connection configuration (per organization)."""

    __tablename__ = "woo_stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Store")
    store_url: Mapped[str] = mapped_column(String(500), nullable=False)
    consumer_key: Mapped[str] = mapped_column(String(255), nullable=False)
    consumer_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    api_version: Mapped[str] = mapped_column(String(20), default="wc/v3")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Sync defaults
    create_as_draft: Mapped[bool] = mapped_column(Boolean, default=True)
    update_prices: Mapped[bool] = mapped_column(Boolean, default=True)
    create_new_products: Mapped[bool] = mapped_column(Boolean, default=False)
    unpublish_discontinued: Mapped[bool] = mapped_column(Boolean, default=False)
    verify_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
