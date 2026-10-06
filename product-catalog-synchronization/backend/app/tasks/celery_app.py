"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "pcr",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.reconciliation_tasks", "app.tasks.woocommerce_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # one heavy job at a time per worker
    task_soft_time_limit=60 * 30,  # 30 min soft
    task_time_limit=60 * 45,  # 45 min hard
    result_expires=60 * 60 * 24 * 7,  # keep results 7 days
)


@celery_app.task(bind=True)
def debug_task(self):
    """Simple health-check task."""
    return {"status": "ok", "task_id": self.request.id}
