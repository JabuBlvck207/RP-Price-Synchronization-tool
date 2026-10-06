"""File loading and initial extraction for CSV and Excel files.

PDF support will be added in a later phase.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

import polars as pl
import pandas as pd

from app.models.product import ProductRecord


# Standard system fields that users map source columns onto
SYSTEM_FIELDS = [
    "sku",
    "product_id",
    "title",
    "product_type",
    "regular_price",
    "sale_price",
    "brand",
    "status",
    "size",
    "colour",
    "model",
    "parent_sku",
]


class FileProcessor:
    """Loads CSV / Excel files into a list of ProductRecord objects."""

    SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf"}

    def __init__(self, source: str = "supplier"):
        """
        Args:
            source: "supplier" or "woobe"
        """
        if source not in ("supplier", "woobe"):
            raise ValueError("source must be 'supplier' or 'woobe'")
        self.source = source

    def detect_format(self, file_path: str | Path) -> str:
        """Detect file format from extension."""
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".csv":
            return "csv"
        if ext in (".xlsx", ".xls"):
            return "excel"
        if ext == ".pdf":
            return "pdf"
        raise ValueError(f"Unsupported file format: {ext}. Supported: CSV, XLSX, XLS")

    def load_dataframe(
        self,
        file_path: str | Path | bytes | io.BytesIO,
        file_name: Optional[str] = None,
    ) -> pl.DataFrame:
        """Load a CSV or Excel file into a Polars DataFrame.

        Supports file path, bytes, or BytesIO.
        """
        if isinstance(file_path, (str, Path)):
            path = Path(file_path)
            ext = path.suffix.lower()
            if ext == ".csv":
                return pl.read_csv(path, infer_schema_length=10000, ignore_errors=True)
            if ext in (".xlsx", ".xls"):
                # Polars has good Excel support via openpyxl / xlsx2csv
                return pl.read_excel(path, engine="openpyxl")
            raise ValueError(f"Unsupported extension: {ext}")

        # In-memory bytes
        if isinstance(file_path, bytes):
            file_path = io.BytesIO(file_path)

        if file_name is None:
            raise ValueError("file_name is required when loading from bytes")

        ext = Path(file_name).suffix.lower()
        if ext == ".csv":
            return pl.read_csv(file_path, infer_schema_length=10000, ignore_errors=True)
        if ext in (".xlsx", ".xls"):
            return pl.read_excel(file_path, engine="openpyxl")
        raise ValueError(f"Unsupported extension: {ext}")

    def get_columns(self, df: pl.DataFrame) -> list[str]:
        """Return list of column names."""
        return df.columns

    def apply_column_mapping(
        self,
        df: pl.DataFrame,
        column_mapping: dict[str, str],
    ) -> pl.DataFrame:
        """Rename source columns according to the user-provided mapping.

        column_mapping maps: source_column_name -> system_field_name
        """
        # Only keep columns that are mapped, and rename them
        rename_map = {
            src: sys for src, sys in column_mapping.items() if src in df.columns
        }
        if not rename_map:
            # If nothing mapped, try auto-detection heuristics
            return self._auto_map_columns(df)

        selected = list(rename_map.keys())
        return df.select(selected).rename(rename_map)

    def _auto_map_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Best-effort automatic column mapping based on common header names."""
        lower_cols = {c.lower().strip(): c for c in df.columns}
        mapping: dict[str, str] = {}

        # SKU heuristics
        for candidate in ("sku", "product code", "product_code", "item code", "item_code", "code"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "sku"
                break

        # Product ID
        for candidate in ("id", "product id", "product_id", "item id"):
            if candidate in lower_cols and lower_cols[candidate] not in mapping:
                mapping[lower_cols[candidate]] = "product_id"
                break

        # Title / Name
        for candidate in ("title", "name", "product name", "product_name", "description", "product description"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "title"
                break

        # Prices
        for candidate in ("regular price", "regular_price", "price", "selling price", "list price"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "regular_price"
                break

        for candidate in ("sale price", "sale_price", "discount price", "promo price"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "sale_price"
                break

        # Brand
        for candidate in ("brand", "brands", "manufacturer"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "brand"
                break

        # Size / Colour
        for candidate in ("size", "sizes"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "size"
                break
        for candidate in ("colour", "color", "colours", "colors"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "colour"
                break

        # Status / Type
        for candidate in ("status", "product status"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "status"
                break
        for candidate in ("type", "product type", "product_type"):
            if candidate in lower_cols:
                mapping[lower_cols[candidate]] = "product_type"
                break

        if not mapping:
            # Fallback: keep original columns (caller must map later)
            return df

        return df.select(list(mapping.keys())).rename(mapping)

    def to_product_records(
        self,
        df: pl.DataFrame,
        column_mapping: Optional[dict[str, str]] = None,
    ) -> list[ProductRecord]:
        """Convert a DataFrame into a list of ProductRecord objects."""
        if column_mapping:
            df = self.apply_column_mapping(df, column_mapping)
        else:
            df = self._auto_map_columns(df)

        # Ensure we have a consistent set of columns
        for col in SYSTEM_FIELDS:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))

        records: list[ProductRecord] = []
        # Convert to list of dicts for easy iteration
        rows = df.to_dicts()

        for idx, row in enumerate(rows):
            # Keep original raw data for non-mapped columns if present
            raw = {k: v for k, v in row.items() if k not in SYSTEM_FIELDS or v is not None}

            record = ProductRecord(
                source=self.source,
                row_index=idx + 1,  # 1-based
                sku=row.get("sku"),
                product_id=row.get("product_id"),
                title=row.get("title"),
                product_type=row.get("product_type"),
                regular_price=row.get("regular_price"),
                sale_price=row.get("sale_price"),
                brand=row.get("brand"),
                status=row.get("status"),
                size=row.get("size"),
                colour=row.get("colour"),
                model=row.get("model"),
                parent_sku=row.get("parent_sku"),
                attributes={},
                raw_data=raw,
            )
            records.append(record)

        return records

    def process(
        self,
        file_path: str | Path | bytes | io.BytesIO,
        column_mapping: Optional[dict[str, str]] = None,
        file_name: Optional[str] = None,
    ) -> list[ProductRecord]:
        """High-level convenience method: load + map + convert to records."""
        # Route PDFs to the PDF extraction pipeline
        name = file_name or (str(file_path) if isinstance(file_path, (str, Path)) else "")
        if name.lower().endswith(".pdf"):
            from app.engines.pdf_processor import PDFProcessor
            return PDFProcessor(source=self.source).process(
                file_path, column_mapping=column_mapping, file_name=file_name
            )
        df = self.load_dataframe(file_path, file_name=file_name)
        return self.to_product_records(df, column_mapping=column_mapping)
