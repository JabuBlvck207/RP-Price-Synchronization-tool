# Product Catalog Reconciliation & Pricing Synchronization Platform

**Version 2.1** | Supplier Price List → WooCommerce / WOOBE Catalog Reconciliation

Web-based platform that automates comparison and synchronization of supplier product catalogs with an existing WooCommerce catalog.

## Current Status (MVP Phase 1–3)

✅ **Completed**
- Core reconciliation engine (CSV + Excel)
- File loading & auto column detection
- Product normalization
- Matching cascade (SKU → Name → Attributes → Fuzzy)
- Duplicate detection
- Price change detection
- Output file generation
- FastAPI REST API (upload, preview, reconcile, download)
- CLI runner
- **Angular frontend** (dashboard, sync wizard, column mapping, results, history, settings)
- **PostgreSQL** persistence (jobs, orgs, users, suppliers, audit logs)
- **Celery + Redis** background job processing
- SQLite fallback for local development without Docker

✅ **Also completed**
- **PDF extraction** (pdfplumber, PyMuPDF, OCR fallback)
- **WooCommerce REST API** (price updates, product creation, status changes, dry-run)

🚧 **Next**
- Authentication / JWT login
- Alembic migrations
- Multi-tenant SaaS hardening

## Quick Start

### 1. Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run reconciliation via CLI

```bash
# From project root
PYTHONPATH=backend python backend/scripts/run_reconciliation.py \
  data/samples/supplier_pioneer.csv \
  data/samples/woobe_export.csv \
  -o data/outputs/my_run
```

### 3. Start the API server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for interactive Swagger UI.

### 4. Start the Angular frontend

```bash
cd frontend
npm install
npm start
# → http://localhost:4200
```

The UI talks to the API at `http://localhost:8000` (configured in `src/environments/environment.ts`).

### Full stack with Docker (PostgreSQL + Redis + Celery)

```bash
cd docker
docker compose up -d --build
# API:    http://localhost:8000
# Worker: processes jobs from Redis queue
# Postgres: localhost:5432 (user/pass/db: pcr)
# Redis:    localhost:6379
```

### Local API without Docker (SQLite fallback)

```bash
cd backend
pip install -r requirements.txt
# Uses SQLite by default (PCR_USE_SQLITE=true)
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Jobs are stored in `backend/data/pcr.db`. If Celery/Redis is unavailable, jobs process inline when you poll `/jobs/{id}`.

### Celery worker (when Redis is running)

```bash
cd backend
PYTHONPATH=. celery -A app.tasks.celery_app.celery_app worker --loglevel=info
```


### 4. Example API flow

```bash
# Preview a file (get columns + suggested mapping)
curl -F "file=@data/samples/supplier_pioneer.csv" \
     -F "source=supplier" \
     http://localhost:8000/upload/preview

# Start reconciliation
curl -X POST http://localhost:8000/reconcile \
  -F "supplier_file=@data/samples/supplier_pioneer.csv" \
  -F "woobe_file=@data/samples/woobe_export.csv"

# Check job status
curl http://localhost:8000/jobs/{job_id}

# Download results
curl -O http://localhost:8000/jobs/{job_id}/download/reconciliation_report.csv
```

## Architecture (MVP)

```
User / CLI / API
      │
      ▼
FileProcessor (CSV / Excel → ProductRecords)
      │
      ▼
ProductNormalizer (SKU, name, size, colour normalization + duplicate flags)
      │
      ▼
MatchingEngine (cascade)
  1. Exact unique SKU
  2. Exact normalized name
  3. Name + attributes (identity key)
  4. Fuzzy (RapidFuzz) with conflict checks
  5. Review / Unmatched / New
      │
      ▼
ReconciliationEngine (stats + classification)
      │
      ▼
OutputGenerator → CSV reports
```

## Matching Priority (from specification)

| Priority | Method                          | Auto-accept? |
|----------|---------------------------------|--------------|
| 0        | Duplicate / validation flags    | No (Review)  |
| 1        | Exact unique SKU                | Yes          |
| 2        | Exact normalized product name   | Yes (if unique) |
| 3        | Name + attributes identity      | Yes          |
| 4        | Variation-level                 | Partial      |
| 5        | Fuzzy (RapidFuzz)               | Only ≥ 85 and no conflicts |
| 6        | Human review                    | Manual       |
| 7        | Unmatched → NEW                 | N/A          |

## Output Files

| File                          | Description                                      |
|-------------------------------|--------------------------------------------------|
| `woocommerce_updated.csv`     | Matched products with supplier prices applied    |
| `new_products.csv`            | Products only in supplier catalog                |
| `price_changes.csv`           | Products whose prices changed                    |
| `potentially_discontinued.csv`| Products only in WOOBE catalog                   |
| `duplicate_ids.csv`           | SKUs that appear more than once                  |
| `review_required.csv`         | Low-confidence or conflicting matches            |
| `reconciliation_report.csv`   | Full match report                                |
| `reconciliation_stats.json`   | Aggregate statistics                             |

## Project Structure

```
product-catalog-reconciliation/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes (future expansion)
│   │   ├── core/          # Config, settings
│   │   ├── engines/       # Core business logic
│   │   │   ├── file_processor.py
│   │   │   ├── normalizer.py
│   │   │   ├── matcher.py
│   │   │   ├── reconciler.py
│   │   │   └── output_generator.py
│   │   ├── models/        # Pydantic models
│   │   ├── services/      # Future service layer
│   │   ├── utils/         # Normalization helpers
│   │   └── main.py        # FastAPI app
│   ├── scripts/
│   │   └── run_reconciliation.py
│   ├── tests/
│   └── requirements.txt
├── data/
│   ├── samples/           # Test CSV files
│   └── outputs/           # Generated reports
├── frontend/              # Angular (Phase 3)
├── docker/
└── docs/
```

## Technology Stack

| Layer              | Technology                  |
|--------------------|-----------------------------|
| Backend            | Python 3.11+, FastAPI       |
| Data Engine        | Polars, Pandas, RapidFuzz   |
| Frontend (planned) | Angular + Angular Material  |
| Database (planned) | PostgreSQL                  |
| Workers (planned)  | Celery + Redis              |
| PDF (later)        | PyMuPDF / pdfplumber / Tesseract |

## Roadmap Alignment

- **Phase 1** ✅ Reconciliation Engine (CSV/Excel) – *this release*
- **Phase 2** ✅ FastAPI REST API – *this release*
- **Phase 3** Angular frontend
- **Phase 4** PostgreSQL
- **Phase 5** Redis / Celery
- **Phase 6** Production hardening
- **Phase 7** WooCommerce REST API
- **Phase 8** Multi-supplier SaaS
- **Phase 9** AI-assisted matching

PDF support is intentionally deferred until CSV/Excel is solid, as requested.

## PDF Support

Supplier catalogs can be uploaded as PDF. Extraction order:

1. **pdfplumber** – structured tables (preferred)
2. **PyMuPDF** – text extraction + heuristic table parsing
3. **OCR** (Tesseract + pdf2image) – scanned documents

OCR-extracted rows are flagged for human review. Install optional deps:

```bash
pip install pymupdf pdfplumber pdf2image pytesseract
# System: tesseract-ocr, poppler-utils
```

## WooCommerce Integration

### Register a store

```bash
curl -X POST http://localhost:8000/woocommerce/stores \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Store",
    "store_url": "https://mystore.com",
    "consumer_key": "ck_...",
    "consumer_secret": "cs_..."
  }'
```

### Test connection

```bash
curl -X POST http://localhost:8000/woocommerce/stores/1/test
```

### Push reconciliation results

```bash
curl -X POST http://localhost:8000/jobs/{job_id}/sync-woocommerce \
  -H "Content-Type: application/json" \
  -d '{
    "update_prices": true,
    "create_new_products": false,
    "unpublish_discontinued": false,
    "dry_run": true
  }'
```

Safety defaults:
- Only confident matches get price updates
- New products are created as **draft** (review before publish)
- Review-required / duplicate SKUs are never pushed automatically
- `dry_run: true` simulates without writing to the store
