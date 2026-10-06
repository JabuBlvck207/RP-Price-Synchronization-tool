"""Basic tests for the matching engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.product import ProductRecord
from app.engines.normalizer import ProductNormalizer
from app.engines.matcher import MatchingEngine


def _make_record(source, sku, title, brand=None, size=None, colour=None, price=None):
    return ProductRecord(
        source=source,
        row_index=1,
        sku=sku,
        title=title,
        brand=brand,
        size=size,
        colour=colour,
        regular_price=price,
    )


def test_exact_sku_match():
    normalizer = ProductNormalizer()
    matcher = MatchingEngine()

    supplier = normalizer.normalize_dataset([
        _make_record("supplier", "ABC-123", "Test Boot", price=100.0)
    ])
    woobe = normalizer.normalize_dataset([
        _make_record("woobe", "ABC-123", "Test Boot Black", price=90.0)
    ])

    results = matcher.match_all(supplier, woobe)
    assert len(results) == 1
    assert results[0].match_type == "EXACT_SKU"
    assert results[0].confidence_score == 100.0
    assert results[0].status.value == "PRICE_CHANGED"


def test_duplicate_sku():
    normalizer = ProductNormalizer()
    matcher = MatchingEngine()

    supplier = normalizer.normalize_dataset([
        _make_record("supplier", "DUP-1", "Item A"),
        _make_record("supplier", "DUP-1", "Item A"),
    ])
    woobe = normalizer.normalize_dataset([
        _make_record("woobe", "DUP-1", "Item A"),
    ])

    results = matcher.match_all(supplier, woobe)
    assert all(r.status.value == "DUPLICATE_SKU" for r in results)


def test_new_product():
    normalizer = ProductNormalizer()
    matcher = MatchingEngine(fuzzy_threshold=90.0)  # stricter for this test

    supplier = normalizer.normalize_dataset([
        _make_record("supplier", "BRAND-NEW", "Completely New Product XYZ-999"),
    ])
    woobe = normalizer.normalize_dataset([
        _make_record("woobe", "EXISTING", "Old Product ABC"),
    ])

    results = matcher.match_all(supplier, woobe)
    assert results[0].status.value == "NEW"


if __name__ == "__main__":
    test_exact_sku_match()
    test_duplicate_sku()
    test_new_product()
    print("All tests passed.")
