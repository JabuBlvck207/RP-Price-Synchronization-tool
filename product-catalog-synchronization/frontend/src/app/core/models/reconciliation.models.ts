export interface SystemFieldsResponse {
  fields: string[];
}

export interface FilePreview {
  filename: string;
  source: 'supplier' | 'woobe';
  format: string;
  columns: string[];
  row_count: number;
  preview: Record<string, any>[];
  suggested_mapping: Record<string, string>;
  system_fields: string[];
}

export interface JobResponse {
  job_id: string;
  status: string;
  progress: number;
  message: string;
  stats?: ReconciliationStats;
  output_files: string[];
  error?: string | null;
}

export interface ReconciliationStats {
  supplier_products: number;
  woobe_products: number;
  existing: number;
  unchanged: number;
  price_changed: number;
  regular_price_changed: number;
  sale_price_changed: number;
  both_prices_changed: number;
  new_products: number;
  new_variations: number;
  potentially_discontinued: number;
  potentially_discontinued_variations: number;
  unmatched: number;
  duplicate_skus: number;
  review_required: number;
  processing_time_seconds: number;
  job_id: string;
  created_at: string;
}

export interface JobResults {
  job_id: string;
  stats: ReconciliationStats;
  new_products_count: number;
  price_changes_count: number;
  discontinued_count: number;
  review_required_count: number;
  duplicates_count: number;
  matches_sample: MatchSample[];
}

export interface MatchSample {
  supplier_sku: string | null;
  supplier_title: string | null;
  match_type: string;
  confidence: number;
  status: string;
}

export interface JobSummary {
  job_id: string;
  status: string;
  progress: number;
  created_at: string;
  message: string;
}

export type ColumnMapping = Record<string, string>; // source_col -> system_field
