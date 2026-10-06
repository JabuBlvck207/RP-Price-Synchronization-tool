"""
PDF extraction pipeline for supplier catalogs.

Supports:
- Text-based PDFs (native text extraction)
- Table-based PDFs (structured tables via pdfplumber / PyMuPDF)
- Scanned PDFs (OCR via Tesseract when available)
- Mixed documents

Extracted rows are converted into the same ProductRecord structure
used by CSV/Excel so the matching engine stays format-agnostic.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import polars as pl

from app.models.product import ProductRecord

logger = logging.getLogger(__name__)

# Optional heavy dependencies – degrade gracefully if not installed
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


# Heuristic column name patterns → system fields
COLUMN_ALIASES: dict[str, list[str]] = {
    "sku": ["sku", "product code", "product_code", "item code", "item_code", "code", "part number", "part no", "ref", "reference"],
    "product_id": ["id", "product id", "product_id", "item id", "line"],
    "title": ["title", "name", "product name", "product_name", "description", "product description", "item description", "desc"],
    "regular_price": ["regular price", "regular_price", "price", "selling price", "list price", "unit price", "rrp", "retail price", "cost"],
    "sale_price": ["sale price", "sale_price", "discount price", "promo price", "special price", "offer price"],
    "brand": ["brand", "brands", "manufacturer", "make"],
    "size": ["size", "sizes", "sz"],
    "colour": ["colour", "color", "colours", "colors"],
    "status": ["status", "product status", "availability", "stock status"],
    "product_type": ["type", "product type", "product_type", "category"],
}


@dataclass
class PDFExtractionResult:
    """Result of extracting structured data from a PDF."""

    success: bool
    method: str  # text_table | pdfplumber | pymupdf | ocr | failed
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ocr_used: bool = False
    confidence_notes: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)


class PDFProcessor:
    """Extract product tables from supplier PDF catalogs."""

    def __init__(self, source: str = "supplier", ocr_enabled: bool = True):
        self.source = source
        self.ocr_enabled = ocr_enabled and HAS_OCR

    def process(
        self,
        file_path: str | Path | bytes | io.BytesIO,
        column_mapping: Optional[dict[str, str]] = None,
        file_name: Optional[str] = None,
    ) -> list[ProductRecord]:
        """Full pipeline: extract → map columns → ProductRecords."""
        result = self.extract(file_path)
        if not result.success or not result.rows:
            raise ValueError(
                "; ".join(result.errors) or "PDF extraction produced no product rows"
            )

        df = pl.DataFrame(result.rows)
        # Normalize column names to strings
        df = df.rename({c: str(c).strip() for c in df.columns})

        if column_mapping:
            rename = {src: sys for src, sys in column_mapping.items() if src in df.columns}
            if rename:
                df = df.select(list(rename.keys())).rename(rename)
        else:
            df = self._auto_map_columns(df)

        return self._to_records(df, result)

    def extract(self, file_path: str | Path | bytes | io.BytesIO) -> PDFExtractionResult:
        """Try multiple extraction strategies in order of reliability."""
        data = self._read_bytes(file_path)
        warnings: list[str] = []
        errors: list[str] = []

        page_count = self._page_count(data)

        # Strategy 1: pdfplumber tables (best for structured price lists)
        if HAS_PDFPLUMBER:
            try:
                result = self._extract_pdfplumber(data)
                if result.success and result.row_count > 0:
                    result.page_count = page_count
                    return result
                warnings.extend(result.warnings)
                errors.extend(result.errors)
            except Exception as e:
                warnings.append(f"pdfplumber failed: {e}")

        # Strategy 2: PyMuPDF text + table-ish parsing
        if HAS_PYMUPDF:
            try:
                result = self._extract_pymupdf(data)
                if result.success and result.row_count > 0:
                    result.page_count = page_count
                    return result
                warnings.extend(result.warnings)
                errors.extend(result.errors)
            except Exception as e:
                warnings.append(f"PyMuPDF failed: {e}")

        # Strategy 3: OCR for scanned PDFs
        if self.ocr_enabled:
            try:
                result = self._extract_ocr(data)
                if result.success and result.row_count > 0:
                    result.page_count = page_count
                    result.ocr_used = True
                    result.confidence_notes.append(
                        "OCR was used – verify SKUs and prices carefully"
                    )
                    return result
                warnings.extend(result.warnings)
                errors.extend(result.errors)
            except Exception as e:
                warnings.append(f"OCR failed: {e}")
        elif not HAS_OCR:
            warnings.append("OCR libraries not installed – scanned PDFs cannot be processed")

        return PDFExtractionResult(
            success=False,
            method="failed",
            page_count=page_count,
            warnings=warnings,
            errors=errors or ["Could not extract structured product data from PDF"],
        )

    def preview(self, file_path: str | Path | bytes | io.BytesIO) -> dict[str, Any]:
        """Return extraction preview suitable for the column-mapping UI."""
        result = self.extract(file_path)
        suggested = {}
        if result.columns:
            # Build suggested mapping from detected headers
            lower_map = {c.lower().strip(): c for c in result.columns}
            for sys_field, aliases in COLUMN_ALIASES.items():
                for alias in aliases:
                    if alias in lower_map:
                        suggested[lower_map[alias]] = sys_field
                        break

        return {
            "success": result.success,
            "method": result.method,
            "ocr_used": result.ocr_used,
            "page_count": result.page_count,
            "columns": result.columns,
            "row_count": result.row_count,
            "preview": result.rows[:10],
            "suggested_mapping": suggested,
            "warnings": result.warnings,
            "errors": result.errors,
            "confidence_notes": result.confidence_notes,
        }

    # ------------------------------------------------------------------
    # Extraction strategies
    # ------------------------------------------------------------------
    def _extract_pdfplumber(self, data: bytes) -> PDFExtractionResult:
        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        warnings: list[str] = []

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    header = [_clean_header(c) for c in table[0]]
                    # Skip tables that look non-product (too few cols)
                    if len([h for h in header if h]) < 2:
                        continue
                    if not columns:
                        columns = header
                    for raw_row in table[1:]:
                        if not raw_row or all(c is None or str(c).strip() == "" for c in raw_row):
                            continue
                        row_dict = {}
                        for i, col in enumerate(header):
                            if not col:
                                continue
                            val = raw_row[i] if i < len(raw_row) else None
                            row_dict[col] = _clean_cell(val)
                        if any(v for v in row_dict.values()):
                            rows.append(row_dict)

        if not rows:
            return PDFExtractionResult(
                success=False,
                method="pdfplumber",
                warnings=["No tables found via pdfplumber"],
            )

        # Unify columns across pages
        all_cols = list(dict.fromkeys(columns + [k for r in rows for k in r.keys()]))
        normalized = [{c: r.get(c) for c in all_cols} for r in rows]

        return PDFExtractionResult(
            success=True,
            method="pdfplumber",
            columns=all_cols,
            rows=normalized,
        )

    def _extract_pymupdf(self, data: bytes) -> PDFExtractionResult:
        if not HAS_PYMUPDF:
            return PDFExtractionResult(success=False, method="pymupdf", errors=["PyMuPDF not installed"])

        doc = fitz.open(stream=data, filetype="pdf")
        all_text_lines: list[str] = []
        for page in doc:
            all_text_lines.extend(page.get_text("text").splitlines())
        doc.close()

        # Try to detect a header line and tabular data
        rows, columns = self._parse_text_as_table(all_text_lines)
        if not rows:
            return PDFExtractionResult(
                success=False,
                method="pymupdf",
                warnings=["Could not parse tabular structure from text"],
            )
        return PDFExtractionResult(
            success=True,
            method="pymupdf",
            columns=columns,
            rows=rows,
        )

    def _extract_ocr(self, data: bytes) -> PDFExtractionResult:
        if not HAS_OCR:
            return PDFExtractionResult(success=False, method="ocr", errors=["OCR not available"])

        images = convert_from_bytes(data, dpi=200)
        all_lines: list[str] = []
        for img in images:
            text = pytesseract.image_to_string(img)
            all_lines.extend(text.splitlines())

        rows, columns = self._parse_text_as_table(all_lines)
        if not rows:
            return PDFExtractionResult(
                success=False,
                method="ocr",
                warnings=["OCR produced text but no tabular product data detected"],
            )
        return PDFExtractionResult(
            success=True,
            method="ocr",
            columns=columns,
            rows=rows,
            ocr_used=True,
        )

    # ------------------------------------------------------------------
    # Text table heuristics
    # ------------------------------------------------------------------
    def _parse_text_as_table(
        self, lines: list[str]
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Heuristic: find a header line containing known column keywords,
        then parse subsequent lines as delimited rows.
        """
        header_idx = None
        header_cols: list[str] = []

        for i, line in enumerate(lines):
            lower = line.lower()
            hits = sum(
                1
                for aliases in COLUMN_ALIASES.values()
                for a in aliases
                if a in lower
            )
            if hits >= 2:
                # Split header by multiple spaces or tabs
                parts = re.split(r"\s{2,}|\t", line.strip())
                if len(parts) >= 2:
                    header_idx = i
                    header_cols = [_clean_header(p) for p in parts]
                    break

        if header_idx is None or not header_cols:
            # Fallback: look for price-like patterns and treat each line as a product
            return self._parse_lines_as_products(lines), ["raw_text", "sku", "title", "regular_price"]

        rows: list[dict[str, Any]] = []
        for line in lines[header_idx + 1 :]:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) < 2:
                continue
            row = {}
            for i, col in enumerate(header_cols):
                if i < len(parts):
                    row[col] = _clean_cell(parts[i])
            if any(row.values()):
                rows.append(row)

        return rows, header_cols

    def _parse_lines_as_products(self, lines: list[str]) -> list[dict[str, Any]]:
        """Last-resort: extract SKU-like tokens and prices from free text lines."""
        rows = []
        sku_re = re.compile(r"\b([A-Z0-9][A-Z0-9\-]{3,20})\b")
        price_re = re.compile(r"(?:R|\$|€|£)?\s*(\d+[.,]\d{2})\b")

        for line in lines:
            line = line.strip()
            if len(line) < 5:
                continue
            skus = sku_re.findall(line)
            prices = price_re.findall(line)
            if not skus and not prices:
                continue
            rows.append({
                "raw_text": line,
                "sku": skus[0] if skus else None,
                "title": line,
                "regular_price": prices[0].replace(",", ".") if prices else None,
            })
        return rows

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_bytes(self, file_path: str | Path | bytes | io.BytesIO) -> bytes:
        if isinstance(file_path, bytes):
            return file_path
        if isinstance(file_path, io.BytesIO):
            return file_path.read()
        return Path(file_path).read_bytes()

    def _page_count(self, data: bytes) -> int:
        if HAS_PYMUPDF:
            try:
                doc = fitz.open(stream=data, filetype="pdf")
                n = len(doc)
                doc.close()
                return n
            except Exception:
                pass
        return 0

    def _auto_map_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        lower_cols = {c.lower().strip(): c for c in df.columns}
        mapping: dict[str, str] = {}
        for sys_field, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in lower_cols and lower_cols[alias] not in mapping:
                    mapping[lower_cols[alias]] = sys_field
                    break
        if not mapping:
            return df
        return df.select(list(mapping.keys())).rename(mapping)

    def _to_records(self, df: pl.DataFrame, extraction: PDFExtractionResult) -> list[ProductRecord]:
        system_fields = [
            "sku", "product_id", "title", "product_type", "regular_price",
            "sale_price", "brand", "status", "size", "colour", "model", "parent_sku",
        ]
        for col in system_fields:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))

        records = []
        for idx, row in enumerate(df.to_dicts()):
            errors = []
            if extraction.ocr_used:
                errors.append("Extracted via OCR – verify accuracy")
            records.append(
                ProductRecord(
                    source=self.source,
                    row_index=idx + 1,
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
                    raw_data={k: v for k, v in row.items() if v is not None},
                )
            )
        return records


def _clean_header(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"\s+", " ", str(val).strip())


def _clean_cell(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None
