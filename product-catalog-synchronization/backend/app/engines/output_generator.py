"""Generate output CSV files from a ReconciliationResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import polars as pl

from app.models.product import (
    ReconciliationResult,
    NormalizedProduct,
    MatchResult,
    ProductRecord,
)


class OutputGenerator:
    """Writes the standard set of reconciliation output files."""

    def _product_to_row(self, p: NormalizedProduct) -> dict[str, Any]:
        return {
            "sku": p.sku,
            "product_id": p.product_id,
            "title": p.title,
            "brand": p.brand,
            "size": p.size,
            "colour": p.colour,
            "regular_price": p.regular_price,
            "sale_price": p.sale_price,
            "status": p.status,
            "row_index": p.row_index,
            "source": p.source,
        }

    def _match_to_row(self, m: MatchResult) -> dict[str, Any]:
        s = m.supplier_product
        w = m.woobe_product
        return {
            "supplier_sku": s.sku,
            "supplier_title": s.title,
            "supplier_regular_price": s.regular_price,
            "supplier_sale_price": s.sale_price,
            "woobe_sku": w.sku if w else None,
            "woobe_title": w.title if w else None,
            "woobe_regular_price": w.regular_price if w else None,
            "woobe_sale_price": w.sale_price if w else None,
            "match_type": m.match_type,
            "confidence_score": m.confidence_score,
            "confidence_class": m.confidence_class.value,
            "status": m.status.value,
            "price_change_type": m.price_change_type.value,
            "requires_review": m.requires_review,
            "match_reasons": "; ".join(m.match_reasons),
            "conflict_reasons": "; ".join(m.conflict_reasons),
        }

    def generate_all(
        self,
        result: ReconciliationResult,
        output_dir: str | Path,
        original_woobe_records: Optional[list[ProductRecord]] = None,
    ) -> dict[str, Path]:
        """Generate all standard output files.

        Returns a dict of logical_name -> file_path.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        files: dict[str, Path] = {}

        # 1. New products
        if result.new_products:
            path = out / "new_products.csv"
            df = pl.DataFrame([self._product_to_row(p) for p in result.new_products])
            df.write_csv(path)
            files["new_products"] = path

        # 2. New variations
        if result.new_variations:
            path = out / "new_variations.csv"
            df = pl.DataFrame([self._product_to_row(p) for p in result.new_variations])
            df.write_csv(path)
            files["new_variations"] = path

        # 3. Potentially discontinued
        if result.discontinued:
            path = out / "potentially_discontinued.csv"
            df = pl.DataFrame([self._product_to_row(p) for p in result.discontinued])
            df.write_csv(path)
            files["potentially_discontinued"] = path

        # 4. Price changes
        if result.price_changes:
            path = out / "price_changes.csv"
            df = pl.DataFrame([self._match_to_row(m) for m in result.price_changes])
            df.write_csv(path)
            files["price_changes"] = path

        # 5. Unmatched
        if result.unmatched:
            path = out / "unmatched_products.csv"
            df = pl.DataFrame([self._product_to_row(p) for p in result.unmatched])
            df.write_csv(path)
            files["unmatched_products"] = path

        # 6. Duplicates
        if result.duplicates:
            path = out / "duplicate_ids.csv"
            df = pl.DataFrame([self._product_to_row(p) for p in result.duplicates])
            df.write_csv(path)
            files["duplicate_ids"] = path

        # 7. Review queue
        if result.review_queue:
            path = out / "review_required.csv"
            df = pl.DataFrame([self._match_to_row(m) for m in result.review_queue])
            df.write_csv(path)
            files["review_required"] = path

        # 8. Full reconciliation report (all matches)
        path = out / "reconciliation_report.csv"
        df = pl.DataFrame([self._match_to_row(m) for m in result.matches])
        df.write_csv(path)
        files["reconciliation_report"] = path

        # 9. Updated WooCommerce file (price sync only)
        # For MVP we produce a simplified updated price file.
        # A full column-preserving update requires the original WOOBE DataFrame.
        updated_rows = []
        for m in result.matches:
            if m.woobe_product and m.status.value in (
                "UNCHANGED",
                "PRICE_CHANGED",
                "EXISTING",
                "ACTIVE",
            ):
                updated_rows.append(
                    {
                        "sku": m.woobe_product.sku,
                        "title": m.woobe_product.title,
                        "regular_price": m.supplier_product.regular_price
                        if m.supplier_product.regular_price is not None
                        else m.woobe_product.regular_price,
                        "sale_price": m.supplier_product.sale_price
                        if m.supplier_product.sale_price is not None
                        else m.woobe_product.sale_price,
                        "status": m.status.value,
                        "price_change_type": m.price_change_type.value,
                    }
                )
        if updated_rows:
            path = out / "woocommerce_updated.csv"
            pl.DataFrame(updated_rows).write_csv(path)
            files["woocommerce_updated"] = path

        # 10. Stats summary
        path = out / "reconciliation_stats.json"
        import json
        with open(path, "w") as f:
            json.dump(result.stats.model_dump(mode="json"), f, indent=2, default=str)
        files["stats"] = path

        return files
