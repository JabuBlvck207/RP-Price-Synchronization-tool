"""Core product data models for the reconciliation engine."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class ProductStatus(str, Enum):
    """Status of a product after reconciliation."""

    EXISTING = "EXISTING"
    UNCHANGED = "UNCHANGED"
    PRICE_CHANGED = "PRICE_CHANGED"
    NEW = "NEW"
    NEW_VARIATION = "NEW_VARIATION"
    POTENTIALLY_DISCONTINUED = "POTENTIALLY_DISCONTINUED"
    POTENTIALLY_DISCONTINUED_VARIATION = "POTENTIALLY_DISCONTINUED_VARIATION"
    UNMATCHED = "UNMATCHED"
    DUPLICATE_SKU = "DUPLICATE_SKU"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ACTIVE = "ACTIVE"


class PriceChangeType(str, Enum):
    """Classification of price changes."""

    REGULAR_PRICE_CHANGED = "REGULAR_PRICE_CHANGED"
    SALE_PRICE_CHANGED = "SALE_PRICE_CHANGED"
    BOTH_PRICES_CHANGED = "BOTH_PRICES_CHANGED"
    PRICE_UNCHANGED = "PRICE_UNCHANGED"
    NO_PRICE_DATA = "NO_PRICE_DATA"


class MatchConfidence(str, Enum):
    """Confidence classification for matches."""

    VERY_HIGH = "VERY_HIGH"      # 95-100
    HIGH = "HIGH"                # 85-94
    MEDIUM = "MEDIUM"            # 70-84
    LOW = "LOW"                  # 50-69
    VERY_LOW = "VERY_LOW"        # 0-49


class ProductRecord(BaseModel):
    """Raw product record as loaded from a file (supplier or WOOBE)."""

    source: str = Field(..., description="supplier | woobe")
    row_index: int = Field(..., description="Original row number in source file")
    sku: Optional[str] = None
    product_id: Optional[str] = None
    title: Optional[str] = None
    product_type: Optional[str] = None
    regular_price: Optional[float] = None
    sale_price: Optional[float] = None
    brand: Optional[str] = None
    status: Optional[str] = None
    size: Optional[str] = None
    colour: Optional[str] = None
    model: Optional[str] = None
    parent_sku: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("regular_price", "sale_price", mode="before")
    @classmethod
    def parse_price(cls, v: Any) -> Optional[float]:
        if v is None or v == "" or str(v).strip().upper() in ("N/A", "NA", "-", "NONE"):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # Clean currency symbols and whitespace
        s = str(v).strip()
        for sym in ("R", "$", "€", "£", ",", " "):
            s = s.replace(sym, "")
        try:
            return float(s)
        except (ValueError, TypeError):
            return None


class NormalizedProduct(BaseModel):
    """Normalized product ready for matching."""

    source: str
    row_index: int
    sku: Optional[str] = None
    sku_normalized: Optional[str] = None
    product_id: Optional[str] = None
    title: Optional[str] = None
    title_normalized: Optional[str] = None
    product_type: Optional[str] = None
    regular_price: Optional[float] = None
    sale_price: Optional[float] = None
    brand: Optional[str] = None
    brand_normalized: Optional[str] = None
    status: Optional[str] = None
    size: Optional[str] = None
    size_normalized: Optional[str] = None
    colour: Optional[str] = None
    colour_normalized: Optional[str] = None
    model: Optional[str] = None
    parent_sku: Optional[str] = None
    identity_key: Optional[str] = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    is_duplicate_sku: bool = False
    is_duplicate_name: bool = False
    validation_errors: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    """Result of matching a supplier product to a WOOBE product."""

    supplier_product: NormalizedProduct
    woobe_product: Optional[NormalizedProduct] = None
    match_type: str = "NONE"  # EXACT_SKU, EXACT_NAME, NAME_ATTRIBUTES, VARIATION, FUZZY, HUMAN_REVIEW, UNMATCHED
    confidence_score: float = 0.0
    confidence_class: MatchConfidence = MatchConfidence.VERY_LOW
    status: ProductStatus = ProductStatus.UNMATCHED
    price_change_type: PriceChangeType = PriceChangeType.NO_PRICE_DATA
    match_reasons: list[str] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)
    requires_review: bool = False
    approved: Optional[bool] = None  # None = not reviewed, True/False after human review


class ReconciliationStats(BaseModel):
    """Aggregate statistics for a reconciliation run."""

    supplier_products: int = 0
    woobe_products: int = 0
    existing: int = 0
    unchanged: int = 0
    price_changed: int = 0
    regular_price_changed: int = 0
    sale_price_changed: int = 0
    both_prices_changed: int = 0
    new_products: int = 0
    new_variations: int = 0
    potentially_discontinued: int = 0
    potentially_discontinued_variations: int = 0
    unmatched: int = 0
    duplicate_skus: int = 0
    review_required: int = 0
    processing_time_seconds: float = 0.0
    job_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReconciliationResult(BaseModel):
    """Full result of a reconciliation run."""

    job_id: str
    stats: ReconciliationStats
    matches: list[MatchResult] = Field(default_factory=list)
    new_products: list[NormalizedProduct] = Field(default_factory=list)
    new_variations: list[NormalizedProduct] = Field(default_factory=list)
    discontinued: list[NormalizedProduct] = Field(default_factory=list)
    discontinued_variations: list[NormalizedProduct] = Field(default_factory=list)
    unmatched: list[NormalizedProduct] = Field(default_factory=list)
    duplicates: list[NormalizedProduct] = Field(default_factory=list)
    review_queue: list[MatchResult] = Field(default_factory=list)
    price_changes: list[MatchResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
