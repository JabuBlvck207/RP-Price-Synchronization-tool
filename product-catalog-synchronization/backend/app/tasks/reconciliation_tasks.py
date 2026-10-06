"""Celery tasks for catalog reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.db.session import SyncSessionLocal
from app.db.models import SyncJobRecord, JobStatusEnum, AuditLog
from app.engines.reconciler import ReconciliationEngine


def _update_job(
    session,
    job_id: str,
    *,
    status: Optional[JobStatusEnum] = None,
    progress: Optional[float] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    stats: Optional[dict] = None,
    output_files: Optional[list] = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
    if not job:
        return
    if status is not None:
        job.status = status.value if hasattr(status, "value") else status
    if progress is not None:
        job.progress = progress
    if message is not None:
        job.message = message
    if error is not None:
        job.error = error
    if stats is not None:
        job.stats = stats
    if output_files is not None:
        job.output_files = output_files
    if started:
        job.started_at = datetime.now(timezone.utc)
    if completed:
        job.completed_at = datetime.now(timezone.utc)
    session.commit()


@celery_app.task(bind=True, name="app.tasks.run_reconciliation")
def run_reconciliation_task(
    self,
    job_id: str,
    supplier_file: str,
    woobe_file: str,
    supplier_mapping: Optional[dict[str, str]] = None,
    woobe_mapping: Optional[dict[str, str]] = None,
    fuzzy_threshold: float = 85.0,
    auto_match_min_score: float = 85.0,
) -> dict[str, Any]:
    """
    Background reconciliation task.

    Updates job progress in PostgreSQL as it runs.
    """
    session = SyncSessionLocal()
    try:
        # Mark started
        _update_job(
            session,
            job_id,
            status=JobStatusEnum.MATCHING,
            progress=5.0,
            message="Starting reconciliation engine...",
            started=True,
        )
        self.update_state(state="STARTED", meta={"progress": 5, "message": "Starting"})

        # Record celery task id
        job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
        if job:
            job.celery_task_id = self.request.id
            session.commit()

        _update_job(
            session,
            job_id,
            status=JobStatusEnum.NORMALIZING,
            progress=15.0,
            message="Loading and normalizing catalogs...",
        )
        self.update_state(state="PROGRESS", meta={"progress": 15, "message": "Normalizing"})

        engine = ReconciliationEngine(
            fuzzy_threshold=fuzzy_threshold,
            auto_match_min_score=auto_match_min_score,
        )

        out_dir = settings.output_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        _update_job(
            session,
            job_id,
            status=JobStatusEnum.MATCHING,
            progress=30.0,
            message="Matching products...",
        )
        self.update_state(state="PROGRESS", meta={"progress": 30, "message": "Matching"})

        result = engine.run(
            supplier_file=supplier_file,
            woobe_file=woobe_file,
            supplier_column_mapping=supplier_mapping,
            woobe_column_mapping=woobe_mapping,
            job_id=job_id,
            output_dir=out_dir,
        )

        if result.errors:
            _update_job(
                session,
                job_id,
                status=JobStatusEnum.FAILED,
                progress=100.0,
                message=f"Failed: {result.errors[0]}",
                error="; ".join(result.errors),
                completed=True,
            )
            # Audit
            job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
            if job:
                session.add(
                    AuditLog(
                        organization_id=job.organization_id,
                        job_id=job.id,
                        action="RECONCILIATION_FAILED",
                        detail="; ".join(result.errors),
                    )
                )
                session.commit()
            return {"status": "FAILED", "errors": result.errors}

        _update_job(
            session,
            job_id,
            status=JobStatusEnum.GENERATING_OUTPUTS,
            progress=85.0,
            message="Generating output files...",
        )
        self.update_state(state="PROGRESS", meta={"progress": 85, "message": "Generating outputs"})

        output_files = sorted([p.name for p in out_dir.glob("*") if p.is_file()])
        stats_dict = result.stats.model_dump(mode="json")

        _update_job(
            session,
            job_id,
            status=JobStatusEnum.COMPLETED,
            progress=100.0,
            message="Reconciliation completed successfully",
            stats=stats_dict,
            output_files=output_files,
            completed=True,
        )

        # Audit success
        job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
        if job:
            session.add(
                AuditLog(
                    organization_id=job.organization_id,
                    job_id=job.id,
                    action="RECONCILIATION_COMPLETED",
                    detail=f"Matched {stats_dict.get('existing', 0)} products, "
                    f"{stats_dict.get('new_products', 0)} new, "
                    f"{stats_dict.get('price_changed', 0)} price changes",
                    meta=stats_dict,
                )
            )
            session.commit()

        self.update_state(state="SUCCESS", meta={"progress": 100, "message": "Done"})
        return {
            "status": "COMPLETED",
            "job_id": job_id,
            "stats": stats_dict,
            "output_files": output_files,
        }

    except Exception as exc:
        _update_job(
            session,
            job_id,
            status=JobStatusEnum.FAILED,
            progress=100.0,
            message=f"Failed: {exc}",
            error=str(exc),
            completed=True,
        )
        job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
        if job:
            session.add(
                AuditLog(
                    organization_id=job.organization_id,
                    job_id=job.id,
                    action="RECONCILIATION_ERROR",
                    detail=str(exc),
                )
            )
            session.commit()
        raise
    finally:
        session.close()
