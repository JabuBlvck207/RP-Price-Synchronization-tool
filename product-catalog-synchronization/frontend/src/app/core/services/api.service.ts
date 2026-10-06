import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  FilePreview,
  JobResponse,
  JobResults,
  JobSummary,
  SystemFieldsResponse,
} from '../models/reconciliation.models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiUrl;

  getSystemFields(): Observable<SystemFieldsResponse> {
    return this.http.get<SystemFieldsResponse>(`${this.base}/system-fields`);
  }

  previewFile(file: File, source: 'supplier' | 'woobe'): Observable<FilePreview> {
    const form = new FormData();
    form.append('file', file);
    form.append('source', source);
    return this.http.post<FilePreview>(`${this.base}/upload/preview`, form);
  }

  startReconciliation(
    supplierFile: File,
    woobeFile: File,
    supplierMapping?: Record<string, string>,
    woobeMapping?: Record<string, string>
  ): Observable<JobResponse> {
    const form = new FormData();
    form.append('supplier_file', supplierFile);
    form.append('woobe_file', woobeFile);
    if (supplierMapping) {
      form.append('supplier_mapping', JSON.stringify(supplierMapping));
    }
    if (woobeMapping) {
      form.append('woobe_mapping', JSON.stringify(woobeMapping));
    }
    return this.http.post<JobResponse>(`${this.base}/reconcile`, form);
  }

  getJob(jobId: string): Observable<JobResponse> {
    return this.http.get<JobResponse>(`${this.base}/jobs/${jobId}`);
  }

  getJobResults(jobId: string): Observable<JobResults> {
    return this.http.get<JobResults>(`${this.base}/jobs/${jobId}/results`);
  }

  listJobs(): Observable<JobSummary[]> {
    return this.http.get<JobSummary[]>(`${this.base}/jobs`);
  }

  getDownloadUrl(jobId: string, fileName: string): string {
    return `${this.base}/jobs/${jobId}/download/${fileName}`;
  }
}
