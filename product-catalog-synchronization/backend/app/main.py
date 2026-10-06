"""FastAPI application entry point – PostgreSQL + Celery backend."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db, async_engine
from app.db.base import Base
from app.db.models import SyncJobRecord, JobStatusEnum, AuditLog
from app.engines.file_processor import FileProcessor, SYSTEM_FIELDS
from app.tasks.reconciliation_tasks import run_reconciliation_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Product Catalog Reconciliation & Pricing Synchronization Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str
    stats: Optional[dict] = None
    output_files: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    celery_task_id: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobSummary(BaseModel):
    job_id: str
    status: str
    progress: float
    created_at: str
    message: str
    supplier_name: Optional[str] = None


def _job_to_response(job: SyncJobRecord) -> JobResponse:
    status = job.status.value if isinstance(job.status, JobStatusEnum) else str(job.status)
    return JobResponse(
        job_id=job.job_id,
        status=status,
        progress=job.progress,
        message=job.message or "",
        stats=job.stats,
        output_files=job.output_files or [],
        error=job.error,
        celery_task_id=job.celery_task_id,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
        "features": ["postgresql", "celery", "csv", "excel", "pdf", "woocommerce"],
    }


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(1))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/system-fields")
def get_system_fields():
    return {"fields": SYSTEM_FIELDS}


@app.post("/upload/preview")
async def preview_file(
    file: UploadFile = File(...),
    source: str = Form("supplier"),
):
    if source not in ("supplier", "woobe"):
        raise HTTPException(400, "source must be 'supplier' or 'woobe'")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Allowed: {sorted(settings.allowed_extensions)}",
        )

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {settings.max_upload_size_mb} MB limit")

    ext = Path(file.filename or "").suffix.lower()

    # PDF path – use dedicated extractor
    if ext == ".pdf":
        from app.engines.pdf_processor import PDFProcessor
        try:
            pdf_preview = PDFProcessor(source=source).preview(content)
        except Exception as e:
            raise HTTPException(400, f"Failed to extract PDF: {e}")
        if not pdf_preview.get("success"):
            raise HTTPException(
                400,
                pdf_preview.get("errors", ["PDF extraction failed"])[0]
                if pdf_preview.get("errors")
                else "PDF extraction failed",
            )
        return {
            "filename": file.filename,
            "source": source,
            "format": "pdf",
            "columns": pdf_preview.get("columns", []),
            "row_count": pdf_preview.get("row_count", 0),
            "preview": pdf_preview.get("preview", []),
            "suggested_mapping": pdf_preview.get("suggested_mapping", {}),
            "system_fields": SYSTEM_FIELDS,
            "extraction_method": pdf_preview.get("method"),
            "ocr_used": pdf_preview.get("ocr_used", False),
            "warnings": pdf_preview.get("warnings", []),
            "confidence_notes": pdf_preview.get("confidence_notes", []),
        }

    processor = FileProcessor(source=source)
    try:
        df = processor.load_dataframe(content, file_name=file.filename)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")

    columns = df.columns
    preview_rows = df.head(10).to_dicts()

    auto_mapped = processor._auto_map_columns(df)
    suggested: dict[str, str] = {}
    for sys_col in auto_mapped.columns:
        for orig in columns:
            if orig.lower().replace(" ", "_") == sys_col or orig.lower() == sys_col:
                suggested[orig] = sys_col
                break

    return {
        "filename": file.filename,
        "source": source,
        "format": processor.detect_format(file.filename or "file.csv"),
        "columns": columns,
        "row_count": df.height,
        "preview": preview_rows,
        "suggested_mapping": suggested,
        "system_fields": SYSTEM_FIELDS,
    }


@app.post("/reconcile", response_model=JobResponse)
async def start_reconciliation(
    supplier_file: UploadFile = File(...),
    woobe_file: UploadFile = File(...),
    supplier_mapping: Optional[str] = Form(None),
    woobe_mapping: Optional[str] = Form(None),
    supplier_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    job_id = f"SYNC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    supplier_ext = Path(supplier_file.filename or ".csv").suffix
    woobe_ext = Path(woobe_file.filename or ".csv").suffix
    supplier_path = settings.upload_dir / f"{job_id}_supplier{supplier_ext}"
    woobe_path = settings.upload_dir / f"{job_id}_woobe{woobe_ext}"

    supplier_content = await supplier_file.read()
    woobe_content = await woobe_file.read()
    supplier_path.write_bytes(supplier_content)
    woobe_path.write_bytes(woobe_content)

    supp_map = json.loads(supplier_mapping) if supplier_mapping else None
    woobe_map = json.loads(woobe_mapping) if woobe_mapping else None

    job = SyncJobRecord(
        job_id=job_id,
        status=JobStatusEnum.PENDING.value,
        progress=0.0,
        message="Job queued",
        supplier_name=supplier_name or "Unknown",
        supplier_file_path=str(supplier_path),
        supplier_file_name=supplier_file.filename,
        woobe_file_path=str(woobe_path),
        woobe_file_name=woobe_file.filename,
        column_mapping={"supplier": supp_map, "woobe": woobe_map},
        matching_config={
            "fuzzy_threshold": settings.fuzzy_threshold,
            "auto_match_min_score": settings.auto_match_min_score,
        },
    )
    db.add(job)
    db.add(
        AuditLog(
            action="JOB_CREATED",
            detail=f"Reconciliation job {job_id} created",
            meta={"supplier_file": supplier_file.filename, "woobe_file": woobe_file.filename},
        )
    )
    await db.flush()

    try:
        async_result = run_reconciliation_task.delay(
            job_id=job_id,
            supplier_file=str(supplier_path),
            woobe_file=str(woobe_path),
            supplier_mapping=supp_map,
            woobe_mapping=woobe_map,
            fuzzy_threshold=settings.fuzzy_threshold,
            auto_match_min_score=settings.auto_match_min_score,
        )
        job.celery_task_id = async_result.id
        job.message = "Queued for background processing"
    except Exception as e:
        job.message = f"Celery unavailable ({e}); will process inline on status poll"

    await db.commit()
    await db.refresh(job)
    return _job_to_response(job)


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SyncJobRecord).where(SyncJobRecord.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    # Dev fallback: process inline when Celery/Redis is not available
    if (
        job.status == JobStatusEnum.PENDING.value or job.status == "PENDING"
        and not job.celery_task_id
        and job.supplier_file_path
        and job.woobe_file_path
    ):
        from app.engines.reconciler import ReconciliationEngine

        job.status = JobStatusEnum.MATCHING.value
        job.progress = 10.0
        job.message = "Processing inline (no Celery worker)"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            engine = ReconciliationEngine(
                fuzzy_threshold=settings.fuzzy_threshold,
                auto_match_min_score=settings.auto_match_min_score,
            )
            out_dir = settings.output_dir / job_id
            mapping = job.column_mapping or {}
            result_obj = engine.run(
                supplier_file=job.supplier_file_path,
                woobe_file=job.woobe_file_path,
                supplier_column_mapping=mapping.get("supplier"),
                woobe_column_mapping=mapping.get("woobe"),
                job_id=job_id,
                output_dir=out_dir,
            )
            if result_obj.errors:
                job.status = JobStatusEnum.FAILED.value
                job.error = "; ".join(result_obj.errors)
                job.message = f"Failed: {result_obj.errors[0]}"
            else:
                job.status = JobStatusEnum.COMPLETED.value
                job.progress = 100.0
                job.message = "Reconciliation completed successfully"
                job.stats = result_obj.stats.model_dump(mode="json")
                job.output_files = sorted([p.name for p in out_dir.glob("*") if p.is_file()])
            job.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            job.status = JobStatusEnum.FAILED.value
            job.error = str(e)
            job.message = f"Failed: {e}"
            job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(job)

    return _job_to_response(job)


@app.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SyncJobRecord).where(SyncJobRecord.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatusEnum.COMPLETED.value and job.status != "COMPLETED":
        raise HTTPException(400, f"Job is {job.status.value}, results not ready")

    stats = job.stats or {}
    return {
        "job_id": job.job_id,
        "stats": stats,
        "new_products_count": stats.get("new_products", 0),
        "price_changes_count": stats.get("price_changed", 0),
        "discontinued_count": stats.get("potentially_discontinued", 0),
        "review_required_count": stats.get("review_required", 0),
        "duplicates_count": stats.get("duplicate_skus", 0),
        "matches_sample": [],
        "output_files": job.output_files or [],
    }


@app.get("/jobs/{job_id}/download/{file_name}")
async def download_output(job_id: str, file_name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SyncJobRecord).where(SyncJobRecord.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    out_dir = settings.output_dir / job_id
    path = out_dir / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "File not found")
    if not path.resolve().is_relative_to(out_dir.resolve()):
        raise HTTPException(403, "Access denied")
    return FileResponse(path, filename=file_name)


@app.get("/jobs", response_model=list[JobSummary])
async def list_jobs(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SyncJobRecord)
        .order_by(desc(SyncJobRecord.created_at))
        .limit(min(limit, 200))
        .offset(offset)
    )
    jobs = result.scalars().all()
    return [
        JobSummary(
            job_id=j.job_id,
            status=j.status.value if isinstance(j.status, JobStatusEnum) else str(j.status),
            progress=j.progress,
            created_at=j.created_at.isoformat() if j.created_at else "",
            message=j.message or "",
            supplier_name=j.supplier_name,
        )
        for j in jobs
    ]


@app.get("/jobs/{job_id}/audit")
async def get_job_audit(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SyncJobRecord).where(SyncJobRecord.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    logs_result = await db.execute(
        select(AuditLog).where(AuditLog.job_id == job.id).order_by(AuditLog.created_at)
    )
    logs = logs_result.scalars().all()
    return [
        {
            "action": log.action,
            "detail": log.detail,
            "meta": log.meta,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


# ---------------------------------------------------------------------------
# WooCommerce store configuration & sync
# ---------------------------------------------------------------------------
from app.db.models import WooStore
from app.services.woocommerce import WooConfig, WooCommerceClient, WooCommerceAPIError
from app.tasks.woocommerce_tasks import sync_to_woocommerce_task


class WooStoreCreate(BaseModel):
    name: str = "Default Store"
    store_url: str
    consumer_key: str
    consumer_secret: str
    api_version: str = "wc/v3"
    create_as_draft: bool = True
    update_prices: bool = True
    create_new_products: bool = False
    unpublish_discontinued: bool = False
    verify_ssl: bool = True


class WooStoreResponse(BaseModel):
    id: int
    name: str
    store_url: str
    api_version: str
    is_active: bool
    create_as_draft: bool
    update_prices: bool
    create_new_products: bool
    unpublish_discontinued: bool


class WooSyncRequest(BaseModel):
    store_id: Optional[int] = None
    update_prices: bool = True
    create_new_products: bool = False
    unpublish_discontinued: bool = False
    create_as_draft: bool = True
    dry_run: bool = False


@app.post("/woocommerce/stores", response_model=WooStoreResponse)
async def create_woo_store(body: WooStoreCreate, db: AsyncSession = Depends(get_db)):
    """Register a WooCommerce store connection."""
    store = WooStore(
        name=body.name,
        store_url=body.store_url.rstrip("/"),
        consumer_key=body.consumer_key,
        consumer_secret=body.consumer_secret,
        api_version=body.api_version,
        create_as_draft=body.create_as_draft,
        update_prices=body.update_prices,
        create_new_products=body.create_new_products,
        unpublish_discontinued=body.unpublish_discontinued,
        verify_ssl=body.verify_ssl,
        is_active=True,
    )
    db.add(store)
    await db.flush()
    await db.refresh(store)
    return WooStoreResponse(
        id=store.id,
        name=store.name,
        store_url=store.store_url,
        api_version=store.api_version,
        is_active=store.is_active,
        create_as_draft=store.create_as_draft,
        update_prices=store.update_prices,
        create_new_products=store.create_new_products,
        unpublish_discontinued=store.unpublish_discontinued,
    )


@app.get("/woocommerce/stores", response_model=list[WooStoreResponse])
async def list_woo_stores(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WooStore).where(WooStore.is_active == True))  # noqa: E712
    stores = result.scalars().all()
    return [
        WooStoreResponse(
            id=s.id,
            name=s.name,
            store_url=s.store_url,
            api_version=s.api_version,
            is_active=s.is_active,
            create_as_draft=s.create_as_draft,
            update_prices=s.update_prices,
            create_new_products=s.create_new_products,
            unpublish_discontinued=s.unpublish_discontinued,
        )
        for s in stores
    ]


@app.post("/woocommerce/stores/{store_id}/test")
async def test_woo_store(store_id: int, db: AsyncSession = Depends(get_db)):
    """Test WooCommerce API credentials."""
    result = await db.execute(select(WooStore).where(WooStore.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(404, "Store not found")
    config = WooConfig(
        store_url=store.store_url,
        consumer_key=store.consumer_key,
        consumer_secret=store.consumer_secret,
        api_version=store.api_version or "wc/v3",
        verify_ssl=store.verify_ssl,
    )
    try:
        with WooCommerceClient(config) as client:
            return client.test_connection()
    except WooCommerceAPIError as e:
        raise HTTPException(400, f"Connection failed: {e.message}")
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")


@app.post("/jobs/{job_id}/sync-woocommerce")
async def sync_job_to_woocommerce(
    job_id: str,
    body: WooSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Push a completed reconciliation job to WooCommerce.

    By default only updates prices for confidently matched products.
    Set create_new_products=true to also create missing products (as draft).
    Set dry_run=true to simulate without writing to the store.
    """
    result = await db.execute(select(SyncJobRecord).where(SyncJobRecord.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("COMPLETED",):
        raise HTTPException(400, f"Job must be COMPLETED (currently {job.status})")

    # Try Celery first
    try:
        async_result = sync_to_woocommerce_task.delay(
            job_id=job_id,
            store_id=body.store_id,
            update_prices=body.update_prices,
            create_new_products=body.create_new_products,
            unpublish_discontinued=body.unpublish_discontinued,
            create_as_draft=body.create_as_draft,
            dry_run=body.dry_run,
        )
        return {
            "status": "queued",
            "celery_task_id": async_result.id,
            "job_id": job_id,
            "dry_run": body.dry_run,
        }
    except Exception:
        # Inline fallback
        from app.tasks.woocommerce_tasks import sync_to_woocommerce_task as _task
        report = _task(
            job_id=job_id,
            store_id=body.store_id,
            update_prices=body.update_prices,
            create_new_products=body.create_new_products,
            unpublish_discontinued=body.unpublish_discontinued,
            create_as_draft=body.create_as_draft,
            dry_run=body.dry_run,
        )
        return report
