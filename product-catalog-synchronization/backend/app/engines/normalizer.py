"""Normalize product records and detect basic data quality issues."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from app.models.product import ProductRecord, NormalizedProduct
from app.utils.normalization import (
    normalize_sku,
    normalize_name,
    normalize_size,
    normalize_colour,
    normalize_brand,
    build_identity_key,
)


class ProductNormalizer:
    """Converts raw ProductRecords into NormalizedProducts and flags issues."""

    def normalize_record(self, record: ProductRecord) -> NormalizedProduct:
        """Normalize a single product record."""
        sku_norm = normalize_sku(record.sku)
        title_norm = normalize_name(record.title)
        brand_norm = normalize_brand(record.brand)
        size_norm = normalize_size(record.size)
        colour_norm = normalize_colour(record.colour)

        identity = build_identity_key(
            brand=record.brand,
            title=record.title,
            model=record.model,
            colour=record.colour,
            size=record.size,
        )

        errors: list[str] = []
        if not sku_norm and not title_norm:
            errors.append("Missing both SKU and product title")
        if record.regular_price is not None and record.regular_price < 0:
            errors.append("Negative regular price")
        if record.sale_price is not None and record.sale_price < 0:
            errors.append("Negative sale price")

        return NormalizedProduct(
            source=record.source,
            row_index=record.row_index,
            sku=record.sku,
            sku_normalized=sku_norm,
            product_id=record.product_id,
            title=record.title,
            title_normalized=title_norm,
            product_type=record.product_type,
            regular_price=record.regular_price,
            sale_price=record.sale_price,
            brand=record.brand,
            brand_normalized=brand_norm,
            status=record.status,
            size=record.size,
            size_normalized=size_norm,
            colour=record.colour,
            colour_normalized=colour_norm,
            model=record.model,
            parent_sku=record.parent_sku,
            identity_key=identity,
            attributes=record.attributes,
            raw_data=record.raw_data,
            validation_errors=errors,
        )

    def normalize_dataset(
        self,
        records: list[ProductRecord],
    ) -> list[NormalizedProduct]:
        """Normalize an entire dataset and mark duplicate SKUs / names."""
        normalized = [self.normalize_record(r) for r in records]

        # Detect duplicate SKUs
        sku_counts = Counter(
            p.sku_normalized for p in normalized if p.sku_normalized
        )
        for p in normalized:
            if p.sku_normalized and sku_counts[p.sku_normalized] > 1:
                p.is_duplicate_sku = True
                p.validation_errors.append(
                    f"Duplicate SKU '{p.sku}' appears {sku_counts[p.sku_normalized]} times"
                )

        # Detect duplicate normalized names (only when SKU is missing)
        name_counts = Counter(
            p.title_normalized
            for p in normalized
            if p.title_normalized and not p.sku_normalized
        )
        for p in normalized:
            if (
                p.title_normalized
                and not p.sku_normalized
                and name_counts[p.title_normalized] > 1
            ):
                p.is_duplicate_name = True
                p.validation_errors.append(
                    f"Duplicate product name '{p.title}' appears {name_counts[p.title_normalized]} times"
                )

        return normalized
