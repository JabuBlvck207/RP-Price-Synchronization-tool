"""Product Matching Engine.

Implements the controlled matching cascade defined in the specification:

Priority 0 - Validation / Duplicate detection
Priority 1 - Exact SKU match
Priority 2 - Exact normalized product name match
Priority 3 - Product name + attributes match
Priority 4 - Variation-level matching
Priority 5 - Fuzzy product matching (RapidFuzz)
Priority 6 - Human review
Priority 7 - Unmatched
"""

from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz

from app.models.product import (
    NormalizedProduct,
    MatchResult,
    MatchConfidence,
    ProductStatus,
    PriceChangeType,
)


class MatchingEngine:
    """Matches supplier products against the WOOBE catalog."""

    def __init__(
        self,
        fuzzy_threshold: float = 85.0,
        auto_match_min_score: float = 85.0,
        review_min_score: float = 50.0,
    ):
        self.fuzzy_threshold = fuzzy_threshold
        self.auto_match_min_score = auto_match_min_score
        self.review_min_score = review_min_score

        # Indexes built from WOOBE catalog
        self._sku_index: dict[str, list[NormalizedProduct]] = {}
        self._name_index: dict[str, list[NormalizedProduct]] = {}
        self._identity_index: dict[str, list[NormalizedProduct]] = {}
        self._all_woobe: list[NormalizedProduct] = []

    def build_indexes(self, woobe_products: list[NormalizedProduct]) -> None:
        """Build lookup indexes from the WOOBE catalog for O(1) matching."""
        self._all_woobe = woobe_products
        self._sku_index.clear()
        self._name_index.clear()
        self._identity_index.clear()

        for p in woobe_products:
            if p.sku_normalized:
                self._sku_index.setdefault(p.sku_normalized, []).append(p)
            if p.title_normalized:
                self._name_index.setdefault(p.title_normalized, []).append(p)
            if p.identity_key:
                self._identity_index.setdefault(p.identity_key, []).append(p)

    def _score_to_class(self, score: float) -> MatchConfidence:
        if score >= 95:
            return MatchConfidence.VERY_HIGH
        if score >= 85:
            return MatchConfidence.HIGH
        if score >= 70:
            return MatchConfidence.MEDIUM
        if score >= 50:
            return MatchConfidence.LOW
        return MatchConfidence.VERY_LOW

    def _compare_prices(
        self,
        supplier: NormalizedProduct,
        woobe: NormalizedProduct,
    ) -> PriceChangeType:
        reg_changed = (
            supplier.regular_price is not None
            and woobe.regular_price is not None
            and abs(supplier.regular_price - woobe.regular_price) > 1e-6
        )
        sale_changed = (
            supplier.sale_price is not None
            and woobe.sale_price is not None
            and abs(supplier.sale_price - woobe.sale_price) > 1e-6
        )

        # Also treat presence of a price on one side only as a change
        if supplier.regular_price is not None and woobe.regular_price is None:
            reg_changed = True
        if supplier.sale_price is not None and woobe.sale_price is None:
            sale_changed = True

        if reg_changed and sale_changed:
            return PriceChangeType.BOTH_PRICES_CHANGED
        if reg_changed:
            return PriceChangeType.REGULAR_PRICE_CHANGED
        if sale_changed:
            return PriceChangeType.SALE_PRICE_CHANGED
        if supplier.regular_price is None and supplier.sale_price is None:
            return PriceChangeType.NO_PRICE_DATA
        return PriceChangeType.PRICE_UNCHANGED

    def _attributes_conflict(
        self,
        supplier: NormalizedProduct,
        woobe: NormalizedProduct,
    ) -> list[str]:
        """Return list of conflicting attribute reasons."""
        conflicts: list[str] = []
        if (
            supplier.size_normalized
            and woobe.size_normalized
            and supplier.size_normalized != woobe.size_normalized
        ):
            conflicts.append(
                f"Size conflict: supplier='{supplier.size}' vs woobe='{woobe.size}'"
            )
        if (
            supplier.colour_normalized
            and woobe.colour_normalized
            and supplier.colour_normalized != woobe.colour_normalized
        ):
            conflicts.append(
                f"Colour conflict: supplier='{supplier.colour}' vs woobe='{woobe.colour}'"
            )
        if (
            supplier.brand_normalized
            and woobe.brand_normalized
            and supplier.brand_normalized != woobe.brand_normalized
        ):
            conflicts.append(
                f"Brand conflict: supplier='{supplier.brand}' vs woobe='{woobe.brand}'"
            )
        return conflicts

    def match_one(self, supplier: NormalizedProduct) -> MatchResult:
        """Match a single supplier product against the indexed WOOBE catalog."""

        # Priority 0 – already duplicated → force review
        if supplier.is_duplicate_sku:
            return MatchResult(
                supplier_product=supplier,
                match_type="DUPLICATE_SKU",
                confidence_score=0.0,
                confidence_class=MatchConfidence.VERY_LOW,
                status=ProductStatus.DUPLICATE_SKU,
                requires_review=True,
                match_reasons=["Duplicate SKU detected in supplier file"],
            )

        # ------------------------------------------------------------------
        # Priority 1 – Exact unique SKU match
        # ------------------------------------------------------------------
        if supplier.sku_normalized:
            candidates = self._sku_index.get(supplier.sku_normalized, [])
            if len(candidates) == 1:
                woobe = candidates[0]
                if woobe.is_duplicate_sku:
                    return MatchResult(
                        supplier_product=supplier,
                        woobe_product=woobe,
                        match_type="EXACT_SKU",
                        confidence_score=90.0,
                        confidence_class=MatchConfidence.HIGH,
                        status=ProductStatus.REVIEW_REQUIRED,
                        requires_review=True,
                        match_reasons=["Exact SKU match but WOOBE SKU is duplicated"],
                    )
                # Clean unique SKU match
                price_type = self._compare_prices(supplier, woobe)
                status = (
                    ProductStatus.PRICE_CHANGED
                    if price_type
                    not in (
                        PriceChangeType.PRICE_UNCHANGED,
                        PriceChangeType.NO_PRICE_DATA,
                    )
                    else ProductStatus.UNCHANGED
                )
                return MatchResult(
                    supplier_product=supplier,
                    woobe_product=woobe,
                    match_type="EXACT_SKU",
                    confidence_score=100.0,
                    confidence_class=MatchConfidence.VERY_HIGH,
                    status=status,
                    price_change_type=price_type,
                    match_reasons=["Exact unique SKU match"],
                )
            if len(candidates) > 1:
                return MatchResult(
                    supplier_product=supplier,
                    match_type="EXACT_SKU",
                    confidence_score=60.0,
                    confidence_class=MatchConfidence.LOW,
                    status=ProductStatus.REVIEW_REQUIRED,
                    requires_review=True,
                    match_reasons=[
                        f"SKU '{supplier.sku}' matches {len(candidates)} WOOBE records"
                    ],
                    conflict_reasons=["Multiple WOOBE products share this SKU"],
                )

        # ------------------------------------------------------------------
        # Priority 2 – Exact normalized product name (unique)
        # ------------------------------------------------------------------
        if supplier.title_normalized:
            candidates = self._name_index.get(supplier.title_normalized, [])
            if len(candidates) == 1:
                woobe = candidates[0]
                conflicts = self._attributes_conflict(supplier, woobe)
                if conflicts:
                    return MatchResult(
                        supplier_product=supplier,
                        woobe_product=woobe,
                        match_type="EXACT_NAME",
                        confidence_score=75.0,
                        confidence_class=MatchConfidence.MEDIUM,
                        status=ProductStatus.REVIEW_REQUIRED,
                        requires_review=True,
                        match_reasons=["Exact normalized name match"],
                        conflict_reasons=conflicts,
                    )
                price_type = self._compare_prices(supplier, woobe)
                status = (
                    ProductStatus.PRICE_CHANGED
                    if price_type
                    not in (
                        PriceChangeType.PRICE_UNCHANGED,
                        PriceChangeType.NO_PRICE_DATA,
                    )
                    else ProductStatus.UNCHANGED
                )
                return MatchResult(
                    supplier_product=supplier,
                    woobe_product=woobe,
                    match_type="EXACT_NAME",
                    confidence_score=95.0,
                    confidence_class=MatchConfidence.VERY_HIGH,
                    status=status,
                    price_change_type=price_type,
                    match_reasons=["Exact unique normalized product name match"],
                )
            if len(candidates) > 1:
                # Fall through to attribute / variation matching
                pass

        # ------------------------------------------------------------------
        # Priority 3 – Name + attributes (identity key)
        # ------------------------------------------------------------------
        if supplier.identity_key:
            candidates = self._identity_index.get(supplier.identity_key, [])
            if len(candidates) == 1:
                woobe = candidates[0]
                price_type = self._compare_prices(supplier, woobe)
                status = (
                    ProductStatus.PRICE_CHANGED
                    if price_type
                    not in (
                        PriceChangeType.PRICE_UNCHANGED,
                        PriceChangeType.NO_PRICE_DATA,
                    )
                    else ProductStatus.UNCHANGED
                )
                return MatchResult(
                    supplier_product=supplier,
                    woobe_product=woobe,
                    match_type="NAME_ATTRIBUTES",
                    confidence_score=92.0,
                    confidence_class=MatchConfidence.HIGH,
                    status=status,
                    price_change_type=price_type,
                    match_reasons=["Product name + attributes identity match"],
                )

        # ------------------------------------------------------------------
        # Priority 4 – Variation-level (simplified: same parent title + size)
        # ------------------------------------------------------------------
        # For MVP we treat size / colour as variation discriminators already
        # handled by identity key. More advanced parent-child logic can be
        # added later when parent_sku is reliably present.

        # ------------------------------------------------------------------
        # Priority 5 – Fuzzy name matching (fallback)
        # ------------------------------------------------------------------
        best_score = 0.0
        best_candidate: Optional[NormalizedProduct] = None

        if supplier.title_normalized:
            for woobe in self._all_woobe:
                if not woobe.title_normalized:
                    continue
                score = fuzz.token_sort_ratio(
                    supplier.title_normalized, woobe.title_normalized
                )
                if score > best_score:
                    best_score = score
                    best_candidate = woobe

        if best_candidate and best_score >= self.fuzzy_threshold:
            conflicts = self._attributes_conflict(supplier, best_candidate)
            if conflicts:
                return MatchResult(
                    supplier_product=supplier,
                    woobe_product=best_candidate,
                    match_type="FUZZY",
                    confidence_score=best_score * 0.85,  # penalise for conflicts
                    confidence_class=self._score_to_class(best_score * 0.85),
                    status=ProductStatus.REVIEW_REQUIRED,
                    requires_review=True,
                    match_reasons=[
                        f"Fuzzy name match (score={best_score:.1f})"
                    ],
                    conflict_reasons=conflicts,
                )
            # Clean high-score fuzzy match
            conf_class = self._score_to_class(best_score)
            requires_review = best_score < self.auto_match_min_score
            price_type = self._compare_prices(supplier, best_candidate)
            status = (
                ProductStatus.REVIEW_REQUIRED
                if requires_review
                else (
                    ProductStatus.PRICE_CHANGED
                    if price_type
                    not in (
                        PriceChangeType.PRICE_UNCHANGED,
                        PriceChangeType.NO_PRICE_DATA,
                    )
                    else ProductStatus.UNCHANGED
                )
            )
            return MatchResult(
                supplier_product=supplier,
                woobe_product=best_candidate,
                match_type="FUZZY",
                confidence_score=best_score,
                confidence_class=conf_class,
                status=status,
                price_change_type=price_type,
                requires_review=requires_review,
                match_reasons=[f"Fuzzy name match (score={best_score:.1f})"],
            )

        # ------------------------------------------------------------------
        # Priority 6 / 7 – Review or Unmatched
        # ------------------------------------------------------------------
        if best_candidate and best_score >= self.review_min_score:
            return MatchResult(
                supplier_product=supplier,
                woobe_product=best_candidate,
                match_type="FUZZY",
                confidence_score=best_score,
                confidence_class=self._score_to_class(best_score),
                status=ProductStatus.REVIEW_REQUIRED,
                requires_review=True,
                match_reasons=[
                    f"Low-confidence fuzzy match (score={best_score:.1f})"
                ],
            )

        # Completely unmatched → treat as NEW
        return MatchResult(
            supplier_product=supplier,
            match_type="NONE",
            confidence_score=0.0,
            confidence_class=MatchConfidence.VERY_LOW,
            status=ProductStatus.NEW,
            match_reasons=["No reliable match found in WOOBE catalog"],
        )

    def match_all(
        self,
        supplier_products: list[NormalizedProduct],
        woobe_products: list[NormalizedProduct],
    ) -> list[MatchResult]:
        """Match every supplier product against the WOOBE catalog."""
        self.build_indexes(woobe_products)
        return [self.match_one(p) for p in supplier_products]
