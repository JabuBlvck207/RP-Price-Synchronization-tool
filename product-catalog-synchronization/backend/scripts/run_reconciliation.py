#!/usr/bin/env python3
"""CLI entry point for running a reconciliation job (CSV / Excel)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.reconciler import ReconciliationEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Product Catalog Reconciliation – CSV / Excel"
    )
    parser.add_argument("supplier_file", help="Path to supplier CSV or Excel file")
    parser.add_argument("woobe_file", help="Path to WOOBE / WooCommerce CSV or Excel file")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="./data/outputs",
        help="Directory to write output files (default: ./data/outputs)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=85.0,
        help="Minimum RapidFuzz score for fuzzy matches (default: 85)",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional job identifier",
    )
    args = parser.parse_args()

    engine = ReconciliationEngine(fuzzy_threshold=args.fuzzy_threshold)
    print(f"Starting reconciliation...")
    print(f"  Supplier : {args.supplier_file}")
    print(f"  WOOBE    : {args.woobe_file}")
    print(f"  Output   : {args.output_dir}")

    result = engine.run(
        supplier_file=args.supplier_file,
        woobe_file=args.woobe_file,
        job_id=args.job_id,
        output_dir=args.output_dir,
    )

    if result.errors:
        print("\nERRORS:")
        for e in result.errors:
            print(f"  - {e}")
        sys.exit(1)

    stats = result.stats
    print("\n=== RECONCILIATION COMPLETE ===")
    print(f"Job ID                 : {stats.job_id}")
    print(f"Processing time        : {stats.processing_time_seconds}s")
    print(f"Supplier products      : {stats.supplier_products}")
    print(f"WOOBE products         : {stats.woobe_products}")
    print(f"Existing / Matched     : {stats.existing}")
    print(f"Unchanged              : {stats.unchanged}")
    print(f"Price changes          : {stats.price_changed}")
    print(f"New products           : {stats.new_products}")
    print(f"New variations         : {stats.new_variations}")
    print(f"Potentially discontinued: {stats.potentially_discontinued}")
    print(f"Unmatched              : {stats.unmatched}")
    print(f"Duplicate SKUs         : {stats.duplicate_skus}")
    print(f"Review required        : {stats.review_required}")
    print(f"\nOutput files written to: {args.output_dir}")


if __name__ == "__main__":
    main()
