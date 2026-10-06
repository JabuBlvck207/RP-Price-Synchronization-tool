"""Celery tasks for WooCommerce store synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.tasks.celery_app import celery_app
from app.db.session import SyncSessionLocal
from app.db.models import SyncJobRecord, AuditLog, WooStore
from app.services.woocommerce import (
    WooConfig,
    WooCommerceSyncService,
    WooCommerceClient,
    WooCommerceAPIError,
)
from app.engines.reconciler import ReconciliationEngine
from app.core.config import settings


@celery_app.task(bind=True, name="app.tasks.sync_to_woocommerce")
def sync_to_woocommerce_task(
    self,
    job_id: str,
    store_id: Optional[int] = None,
    *,
    update_prices: bool = True,
    create_new_products: bool = False,
    unpublish_discontinued: bool = False,
    create_as_draft: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Push reconciliation results for `job_id` to a WooCommerce store.

    Re-runs matching in-process if needed, then applies price updates /
    product creation according to the flags.
    """
    session = SyncSessionLocal()
    try:
        job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
        if not job:
            return {"status": "FAILED", "error": f"Job {job_id} not found"}

        if job.status != "COMPLETED":
            return {"status": "FAILED", "error": f"Job is {job.status}, must be COMPLETED"}

        # Resolve store credentials
        store: Optional[WooStore] = None
        if store_id:
            store = session.query(WooStore).filter(WooStore.id == store_id).first()
        if not store:
            store = session.query(WooStore).filter(WooStore.is_active == True).first()  # noqa: E712
        if not store:
            return {"status": "FAILED", "error": "No active WooCommerce store configured"}

        config = WooConfig(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
            api_version=store.api_version or "wc/v3",
            verify_ssl=store.verify_ssl,
        )

        # Re-run engine to get structured matches (outputs are on disk; we need objects)
        self.update_state(state="PROGRESS", meta={"message": "Re-running reconciliation for sync"})
        engine = ReconciliationEngine(
            fuzzy_threshold=settings.fuzzy_threshold,
            auto_match_min_score=settings.auto_match_min_score,
        )
        mapping = job.column_mapping or {}
        result = engine.run(
            supplier_file=job.supplier_file_path,
            woobe_file=job.woobe_file_path,
            supplier_column_mapping=mapping.get("supplier"),
            woobe_column_mapping=mapping.get("woobe"),
            job_id=job_id,
            output_dir=None,  # don't overwrite files
        )

        if result.errors:
            return {"status": "FAILED", "error": "; ".join(result.errors)}

        sync_service = WooCommerceSyncService(
            config,
            create_as_draft=create_as_draft if create_as_draft is not None else store.create_as_draft,
            update_prices=update_prices if update_prices is not None else store.update_prices,
            create_new_products=create_new_products
            if create_new_products is not None
            else store.create_new_products,
            unpublish_discontinued=unpublish_discontinued
            if unpublish_discontinued is not None
            else store.unpublish_discontinued,
            dry_run=dry_run,
        )

        self.update_state(state="PROGRESS", meta={"message": "Pushing updates to WooCommerce"})
        report = sync_service.sync_from_reconciliation(
            job_id=job_id,
            matches=result.matches,
            new_products=result.new_products,
            discontinued=result.discontinued,
        )

        # Persist report on job + audit
        woo_report = report.to_dict()
        stats = dict(job.stats or {})
        stats["woocommerce_sync"] = {
            "prices_updated": report.prices_updated,
            "products_created": report.products_created,
            "variations_created": report.variations_created,
            "status_changed": report.status_changed,
            "skipped": report.skipped,
            "errors": report.errors,
            "dry_run": dry_run,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        job.stats = stats
        session.add(
            AuditLog(
                organization_id=job.organization_id,
                job_id=job.id,
                action="WOOCOMMERCE_SYNC",
                detail=(
                    f"WC sync: {report.prices_updated} prices, "
                    f"{report.products_created} created, {report.errors} errors"
                    + (" [dry-run]" if dry_run else "")
                ),
                meta=woo_report,
            )
        )
        session.commit()

        return {"status": "COMPLETED", "report": woo_report}

    except Exception as exc:
        session.rollback()
        job = session.query(SyncJobRecord).filter(SyncJobRecord.job_id == job_id).first()
        if job:
            session.add(
                AuditLog(
                    organization_id=job.organization_id,
                    job_id=job.id,
                    action="WOOCOMMERCE_SYNC_FAILED",
                    detail=str(exc),
                )
            )
            session.commit()
        raise
    finally:
        session.close()


@celery_app.task(name="app.tasks.test_woocommerce_connection")
def test_woocommerce_connection_task(store_id: int) -> dict[str, Any]:
    """Test WooCommerce API credentials for a stored store config."""
    session = SyncSessionLocal()
    try:
        store = session.query(WooStore).filter(WooStore.id == store_id).first()
        if not store:
            return {"ok": False, "error": "Store not found"}
        config = WooConfig(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
            api_version=store.api_version or "wc/v3",
            verify_ssl=store.verify_ssl,
        )
        with WooCommerceClient(config) as client:
            return client.test_connection()
    except WooCommerceAPIError as e:
        return {"ok": False, "error": str(e), "status_code": e.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        session.close()
