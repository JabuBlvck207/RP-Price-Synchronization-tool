import { Injectable, signal, computed } from '@angular/core';
import {
  FilePreview,
  ColumnMapping,
  JobResponse,
  JobResults,
  ReconciliationStats,
} from '../models/reconciliation.models';

export interface WizardState {
  step: number; // 0=upload, 1=mapping, 2=processing, 3=results
  supplierFile: File | null;
  woobeFile: File | null;
  supplierPreview: FilePreview | null;
  woobePreview: FilePreview | null;
  supplierMapping: ColumnMapping;
  woobeMapping: ColumnMapping;
  currentJob: JobResponse | null;
  results: JobResults | null;
}

@Injectable({ providedIn: 'root' })
export class ReconciliationStateService {
  private state = signal<WizardState>({
    step: 0,
    supplierFile: null,
    woobeFile: null,
    supplierPreview: null,
    woobePreview: null,
    supplierMapping: {},
    woobeMapping: {},
    currentJob: null,
    results: null,
  });

  // Public readonly signals
  readonly step = computed(() => this.state().step);
  readonly supplierFile = computed(() => this.state().supplierFile);
  readonly woobeFile = computed(() => this.state().woobeFile);
  readonly supplierPreview = computed(() => this.state().supplierPreview);
  readonly woobePreview = computed(() => this.state().woobePreview);
  readonly supplierMapping = computed(() => this.state().supplierMapping);
  readonly woobeMapping = computed(() => this.state().woobeMapping);
  readonly currentJob = computed(() => this.state().currentJob);
  readonly results = computed(() => this.state().results);
  readonly stats = computed(() => this.state().results?.stats ?? this.state().currentJob?.stats ?? null);

  readonly canProceedToMapping = computed(
    () => !!this.state().supplierFile && !!this.state().woobeFile
  );

  readonly canStartReconciliation = computed(() => {
    const s = this.state();
    return !!s.supplierFile && !!s.woobeFile;
  });

  setStep(step: number) {
    this.state.update((s) => ({ ...s, step }));
  }

  setSupplierFile(file: File | null, preview: FilePreview | null = null) {
    this.state.update((s) => ({
      ...s,
      supplierFile: file,
      supplierPreview: preview,
      supplierMapping: preview?.suggested_mapping ?? {},
    }));
  }

  setWoobeFile(file: File | null, preview: FilePreview | null = null) {
    this.state.update((s) => ({
      ...s,
      woobeFile: file,
      woobePreview: preview,
      woobeMapping: preview?.suggested_mapping ?? {},
    }));
  }

  setSupplierMapping(mapping: ColumnMapping) {
    this.state.update((s) => ({ ...s, supplierMapping: mapping }));
  }

  setWoobeMapping(mapping: ColumnMapping) {
    this.state.update((s) => ({ ...s, woobeMapping: mapping }));
  }

  setCurrentJob(job: JobResponse | null) {
    this.state.update((s) => ({ ...s, currentJob: job }));
  }

  setResults(results: JobResults | null) {
    this.state.update((s) => ({ ...s, results }));
  }

  reset() {
    this.state.set({
      step: 0,
      supplierFile: null,
      woobeFile: null,
      supplierPreview: null,
      woobePreview: null,
      supplierMapping: {},
      woobeMapping: {},
      currentJob: null,
      results: null,
    });
  }
}
