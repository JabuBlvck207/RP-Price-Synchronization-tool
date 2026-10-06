"""High-level Reconciliation Engine that orchestrates the full pipeline."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.engines.file_processor import FileProcessor
from app.engines.normalizer import ProductNormalizer
from app.engines.matcher import MatchingEngine
from app.engines.output_generator import OutputGenerator
from app.models.product import (
    ReconciliationResult,
    ReconciliationStats,
    ProductStatus,
    MatchResult,
    NormalizedProduct,
)


class ReconciliationEngine:
    """End-to-end reconciliation orchestrator for CSV / Excel files."""

    def __init__(
        self,
        fuzzy_threshold: float = 85.0,
        auto_match_min_score: float = 85.0,
    ):
        self.normalizer = ProductNormalizer()
        self.matcher = MatchingEngine(
            fuzzy_threshold=fuzzy_threshold,
            auto_match_min_score=auto_match_min_score,
        )
        self.output_generator = OutputGenerator()

    def run(
        self,
        supplier_file: str | Path,
        woobe_file: str | Path,
        supplier_column_mapping: Optional[dict[str, str]] = None,
        woobe_column_mapping: Optional[dict[str, str]] = None,
        job_id: Optional[str] = None,
        output_dir: Optional[str | Path] = None,
    ) -> ReconciliationResult:
        """Execute a full reconciliation run.

        Args:
            supplier_file: Path to supplier CSV/XLSX
            woobe_file: Path to WOOBE CSV/XLSX
            supplier_column_mapping: Optional mapping source_col -> system_field
            woobe_column_mapping: Optional mapping for WOOBE file
            job_id: Optional job identifier
            output_dir: Directory to write output CSVs (optional)

        Returns:
            ReconciliationResult with all matches, stats and classified products.
        """
        start = time.perf_counter()
        job_id = job_id or f"SYNC-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Load files
        try:
            supplier_processor = FileProcessor(source="supplier")
            supplier_records = supplier_processor.process(
                supplier_file, column_mapping=supplier_column_mapping
            )
        except Exception as e:
            errors.append(f"Failed to load supplier file: {e}")
            return self._empty_result(job_id, errors)

        try:
            woobe_processor = FileProcessor(source="woobe")
            woobe_records = woobe_processor.process(
                woobe_file, column_mapping=woobe_column_mapping
            )
        except Exception as e:
            errors.append(f"Failed to load WOOBE file: {e}")
            return self._empty_result(job_id, errors)

        if not supplier_records:
            errors.append("Supplier file contains no product records")
        if not woobe_records:
            errors.append("WOOBE file contains no product records")
        if errors:
            return self._empty_result(job_id, errors)

        # 2. Normalize
        supplier_norm = self.normalizer.normalize_dataset(supplier_records)
        woobe_norm = self.normalizer.normalize_dataset(woobe_records)

        # 3. Match
        matches = self.matcher.match_all(supplier_norm, woobe_norm)

        # 4. Classify results
        new_products: list[NormalizedProduct] = []
        new_variations: list[NormalizedProduct] = []
        price_changes: list[MatchResult] = []
        review_queue: list[MatchResult] = []
        unmatched: list[NormalizedProduct] = []
        duplicates: list[NormalizedProduct] = []

        matched_woobe_skus: set[str] = set()
        matched_woobe_ids: set[int] = set()  # row_index

        for m in matches:
            if m.status == ProductStatus.NEW:
                new_products.append(m.supplier_product)
            elif m.status == ProductStatus.NEW_VARIATION:
                new_variations.append(m.supplier_product)
            elif m.status == ProductStatus.PRICE_CHANGED:
                price_changes.append(m)
            elif m.status == ProductStatus.DUPLICATE_SKU:
                duplicates.append(m.supplier_product)
            elif m.requires_review or m.status == ProductStatus.REVIEW_REQUIRED:
                review_queue.append(m)
            elif m.status == ProductStatus.UNMATCHED:
                unmatched.append(m.supplier_product)

            if m.woobe_product:
                if m.woobe_product.sku_normalized:
                    matched_woobe_skus.add(m.woobe_product.sku_normalized)
                matched_woobe_ids.add(m.woobe_product.row_index)

        # 5. Detect potentially discontinued (in WOOBE but not matched from supplier)
        discontinued: list[NormalizedProduct] = []
        discontinued_variations: list[NormalizedProduct] = []
        for p in woobe_norm:
            if p.row_index in matched_woobe_ids:
                continue
            if p.sku_normalized and p.sku_normalized in matched_woobe_skus:
                continue
            # Simple heuristic for MVP: treat all unmatched WOOBE as potentially discontinued
            discontinued.append(p)

        # 6. Build statistics
        elapsed = time.perf_counter() - start
        stats = ReconciliationStats(
            supplier_products=len(supplier_norm),
            woobe_products=len(woobe_norm),
            existing=sum(
                1
                for m in matches
                if m.status
                in (ProductStatus.UNCHANGED, ProductStatus.PRICE_CHANGED, ProductStatus.EXISTING, ProductStatus.ACTIVE)
            ),
            unchanged=sum(1 for m in matches if m.status == ProductStatus.UNCHANGED),
            price_changed=len(price_changes),
            regular_price_changed=sum(
                1
                for m in price_changes
                if m.price_change_type.value in ("REGULAR_PRICE_CHANGED", "BOTH_PRICES_CHANGED")
            ),
            sale_price_changed=sum(
                1
                for m in price_changes
                if m.price_change_type.value in ("SALE_PRICE_CHANGED", "BOTH_PRICES_CHANGED")
            ),
            both_prices_changed=sum(
                1 for m in price_changes if m.price_change_type.value == "BOTH_PRICES_CHANGED"
            ),
            new_products=len(new_products),
            new_variations=len(new_variations),
            potentially_discontinued=len(discontinued),
            potentially_discontinued_variations=len(discontinued_variations),
            unmatched=len(unmatched),
            duplicate_skus=len(duplicates),
            review_required=len(review_queue),
            processing_time_seconds=round(elapsed, 3),
            job_id=job_id,
        )

        result = ReconciliationResult(
            job_id=job_id,
            stats=stats,
            matches=matches,
            new_products=new_products,
            new_variations=new_variations,
            discontinued=discontinued,
            discontinued_variations=discontinued_variations,
            unmatched=unmatched,
            duplicates=duplicates,
            review_queue=review_queue,
            price_changes=price_changes,
            errors=errors,
            warnings=warnings,
        )

        # 7. Optionally generate output files
        if output_dir:
            self.output_generator.generate_all(result, output_dir, woobe_records)

        return result

    def _empty_result(self, job_id: str, errors: list[str]) -> ReconciliationResult:
        return ReconciliationResult(
            job_id=job_id,
            stats=ReconciliationStats(job_id=job_id),
            errors=errors,
        )
