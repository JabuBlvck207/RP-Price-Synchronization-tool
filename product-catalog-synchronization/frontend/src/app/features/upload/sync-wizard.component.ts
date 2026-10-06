import { Component, inject, signal, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatStepperModule } from '@angular/material/stepper';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatChipsModule } from '@angular/material/chips';
import { Subscription, interval, switchMap, takeWhile } from 'rxjs';
import { ApiService } from '../../core/services/api.service';
import { ReconciliationStateService } from '../../core/services/reconciliation-state.service';
import { FilePreview } from '../../core/models/reconciliation.models';

const SYSTEM_FIELDS = [
  'sku', 'product_id', 'title', 'product_type', 'regular_price',
  'sale_price', 'brand', 'status', 'size', 'colour', 'model', 'parent_sku',
];

@Component({
  selector: 'app-sync-wizard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatStepperModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    MatProgressBarModule,
    MatProgressSpinnerModule,
    MatTableModule,
    MatSnackBarModule,
    MatChipsModule,
  ],
  template: `
    <div class="wizard">
      <h1>New Synchronization</h1>
      <p class="subtitle">Upload supplier and WooCommerce/WOOBE catalogs, map columns, and reconcile.</p>

      <mat-stepper [linear]="true" #stepper class="stepper">
        <!-- Step 1: Upload -->
        <mat-step [completed]="state.canProceedToMapping()">
          <ng-template matStepLabel>Upload Files</ng-template>

          <div class="upload-grid">
            <!-- Supplier -->
            <mat-card class="upload-card" [class.has-file]="!!state.supplierFile()">
              <div class="card-title">
                <mat-icon>local_shipping</mat-icon>
                Supplier Catalog
              </div>
              <p class="hint">CSV, Excel (XLSX/XLS), or PDF</p>

              @if (!state.supplierFile()) {
                <label class="dropzone">
                  <input type="file" accept=".csv,.xlsx,.xls,.pdf" (change)="onSupplierSelect($event)" hidden />
                  <mat-icon>cloud_upload</mat-icon>
                  <span>Click or drop supplier file</span>
                </label>
              } @else {
                <div class="file-info">
                  <mat-icon>description</mat-icon>
                  <div>
                    <strong>{{ state.supplierFile()!.name }}</strong>
                    <div class="meta">
                      {{ state.supplierPreview()?.row_count | number }} rows ·
                      {{ state.supplierPreview()?.columns?.length }} columns
                    </div>
                  </div>
                  <button mat-icon-button (click)="clearSupplier()">
                    <mat-icon>close</mat-icon>
                  </button>
                </div>
              }

              @if (uploadingSupplier()) {
                <mat-progress-bar mode="indeterminate"></mat-progress-bar>
              }
            </mat-card>

            <!-- WOOBE -->
            <mat-card class="upload-card" [class.has-file]="!!state.woobeFile()">
              <div class="card-title">
                <mat-icon>storefront</mat-icon>
                WooCommerce / WOOBE Export
              </div>
              <p class="hint">CSV, Excel (XLSX/XLS), or PDF</p>

              @if (!state.woobeFile()) {
                <label class="dropzone">
                  <input type="file" accept=".csv,.xlsx,.xls,.pdf" (change)="onWoobeSelect($event)" hidden />
                  <mat-icon>cloud_upload</mat-icon>
                  <span>Click or drop WOOBE file</span>
                </label>
              } @else {
                <div class="file-info">
                  <mat-icon>description</mat-icon>
                  <div>
                    <strong>{{ state.woobeFile()!.name }}</strong>
                    <div class="meta">
                      {{ state.woobePreview()?.row_count | number }} rows ·
                      {{ state.woobePreview()?.columns?.length }} columns
                    </div>
                  </div>
                  <button mat-icon-button (click)="clearWoobe()">
                    <mat-icon>close</mat-icon>
                  </button>
                </div>
              }

              @if (uploadingWoobe()) {
                <mat-progress-bar mode="indeterminate"></mat-progress-bar>
              }
            </mat-card>
          </div>

          <div class="actions">
            <button mat-flat-button color="primary" matStepperNext
                    [disabled]="!state.canProceedToMapping()">
              Next: Column Mapping
              <mat-icon>arrow_forward</mat-icon>
            </button>
          </div>
        </mat-step>

        <!-- Step 2: Column Mapping -->
        <mat-step>
          <ng-template matStepLabel>Column Mapping</ng-template>

          <div class="mapping-section">
            <h3>Supplier Column Mapping</h3>
            <p class="hint">Map source columns to system fields. Suggested mappings are pre-filled.</p>

            @if (state.supplierPreview(); as preview) {
              <div class="mapping-table">
                @for (col of preview.columns; track col) {
                  <div class="mapping-row">
                    <span class="src-col">{{ col }}</span>
                    <mat-icon>arrow_forward</mat-icon>
                    <mat-form-field appearance="outline" subscriptSizing="dynamic">
                      <mat-select
                        [ngModel]="state.supplierMapping()[col] || ''"
                        (ngModelChange)="updateSupplierMapping(col, $event)"
                        placeholder="— skip —">
                        <mat-option value="">— skip —</mat-option>
                        @for (field of systemFields; track field) {
                          <mat-option [value]="field">{{ field }}</mat-option>
                        }
                      </mat-select>
                    </mat-form-field>
                  </div>
                }
              </div>

              <div class="preview-table" *ngIf="preview.preview.length">
                <h4>Data Preview (first rows)</h4>
                <div class="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        @for (col of preview.columns; track col) {
                          <th>{{ col }}</th>
                        }
                      </tr>
                    </thead>
                    <tbody>
                      @for (row of preview.preview.slice(0, 5); track $index) {
                        <tr>
                          @for (col of preview.columns; track col) {
                            <td>{{ row[col] }}</td>
                          }
                        </tr>
                      }
                    </tbody>
                  </table>
                </div>
              </div>
            }
          </div>

          <div class="mapping-section" style="margin-top: 32px">
            <h3>WOOBE Column Mapping</h3>
            @if (state.woobePreview(); as preview) {
              <div class="mapping-table">
                @for (col of preview.columns; track col) {
                  <div class="mapping-row">
                    <span class="src-col">{{ col }}</span>
                    <mat-icon>arrow_forward</mat-icon>
                    <mat-form-field appearance="outline" subscriptSizing="dynamic">
                      <mat-select
                        [ngModel]="state.woobeMapping()[col] || ''"
                        (ngModelChange)="updateWoobeMapping(col, $event)"
                        placeholder="— skip —">
                        <mat-option value="">— skip —</mat-option>
                        @for (field of systemFields; track field) {
                          <mat-option [value]="field">{{ field }}</mat-option>
                        }
                      </mat-select>
                    </mat-form-field>
                  </div>
                }
              </div>
            }
          </div>

          <div class="actions">
            <button mat-button matStepperPrevious>Back</button>
            <button mat-flat-button color="primary" (click)="startReconciliation(stepper)"
                    [disabled]="starting()">
              @if (starting()) {
                <mat-spinner diameter="20"></mat-spinner>
              } @else {
                Start Reconciliation
                <mat-icon>play_arrow</mat-icon>
              }
            </button>
          </div>
        </mat-step>

        <!-- Step 3: Processing -->
        <mat-step>
          <ng-template matStepLabel>Processing</ng-template>

          <div class="processing">
            @if (state.currentJob(); as job) {
              <mat-icon class="proc-icon" [class.done]="job.status === 'COMPLETED'"
                        [class.error]="job.status === 'FAILED'">
                {{ job.status === 'COMPLETED' ? 'check_circle' : job.status === 'FAILED' ? 'error' : 'sync' }}
              </mat-icon>
              <h2>{{ job.message || job.status }}</h2>
              <p class="job-id">{{ job.job_id }}</p>
              <mat-progress-bar
                [mode]="job.status === 'COMPLETED' || job.status === 'FAILED' ? 'determinate' : 'indeterminate'"
                [value]="job.progress">
              </mat-progress-bar>
              <p class="progress-label">{{ job.progress | number: '1.0-0' }}%</p>

              @if (job.status === 'COMPLETED') {
                <button mat-flat-button color="primary" (click)="goToResults()">
                  View Results
                  <mat-icon>arrow_forward</mat-icon>
                </button>
              }
              @if (job.status === 'FAILED') {
                <p class="error-msg">{{ job.error }}</p>
                <button mat-stroked-button (click)="stepper.reset(); state.reset()">Try Again</button>
              }
            } @else {
              <mat-spinner></mat-spinner>
              <p>Starting job...</p>
            }
          </div>
        </mat-step>
      </mat-stepper>
    </div>
  `,
  styles: [
    `
      h1 { margin: 0 0 4px; font-size: 1.75rem; font-weight: 600; }
      .subtitle { color: #64748b; margin: 0 0 24px; }
      .stepper { background: transparent; }
      .upload-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        margin-bottom: 24px;
      }
      @media (max-width: 800px) {
        .upload-grid { grid-template-columns: 1fr; }
      }
      .upload-card {
        padding: 24px;
        min-height: 220px;
      }
      .upload-card.has-file {
        border-color: #22c55e;
      }
      .card-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
        font-size: 1.1rem;
        margin-bottom: 4px;
      }
      .hint { color: #94a3b8; font-size: 0.875rem; margin: 0 0 16px; }
      .dropzone {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 32px;
        cursor: pointer;
        color: #64748b;
        transition: border-color 0.2s, background 0.2s;
      }
      .dropzone:hover {
        border-color: #3b82f6;
        background: #f0f9ff;
      }
      .dropzone mat-icon { font-size: 40px; width: 40px; height: 40px; color: #94a3b8; }
      .file-info {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px;
        background: #f0fdf4;
        border-radius: 8px;
      }
      .file-info mat-icon { color: #22c55e; }
      .file-info .meta { font-size: 0.8rem; color: #64748b; }
      .actions {
        display: flex;
        gap: 12px;
        justify-content: flex-end;
        margin-top: 24px;
      }
      .mapping-section h3 { margin: 0 0 4px; }
      .mapping-table {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-width: 600px;
      }
      .mapping-row {
        display: grid;
        grid-template-columns: 1fr 32px 200px;
        align-items: center;
        gap: 8px;
      }
      .src-col {
        font-family: monospace;
        font-size: 0.875rem;
        background: #f1f5f9;
        padding: 8px 12px;
        border-radius: 6px;
      }
      .preview-table {
        margin-top: 24px;
      }
      .preview-table h4 { margin: 0 0 8px; }
      .table-scroll {
        overflow-x: auto;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.8rem;
      }
      th, td {
        padding: 8px 12px;
        text-align: left;
        border-bottom: 1px solid #e2e8f0;
        white-space: nowrap;
      }
      th { background: #f8fafc; font-weight: 600; }
      .processing {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;
        padding: 48px;
        text-align: center;
      }
      .proc-icon {
        font-size: 64px;
        width: 64px;
        height: 64px;
        color: #3b82f6;
        animation: spin 2s linear infinite;
      }
      .proc-icon.done { color: #22c55e; animation: none; }
      .proc-icon.error { color: #ef4444; animation: none; }
      @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
      }
      .job-id { font-family: monospace; color: #64748b; }
      .progress-label { color: #64748b; }
      .error-msg { color: #ef4444; }
      mat-progress-bar { width: 100%; max-width: 400px; }
    `,
  ],
})
export class SyncWizardComponent implements OnDestroy {
  state = inject(ReconciliationStateService);
  private api = inject(ApiService);
  private router = inject(Router);
  private snack = inject(MatSnackBar);

  systemFields = SYSTEM_FIELDS;
  uploadingSupplier = signal(false);
  uploadingWoobe = signal(false);
  starting = signal(false);

  private pollSub?: Subscription;

  ngOnDestroy() {
    this.pollSub?.unsubscribe();
  }

  onSupplierSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.uploadingSupplier.set(true);
    this.api.previewFile(file, 'supplier').subscribe({
      next: (preview) => {
        this.state.setSupplierFile(file, preview);
        this.uploadingSupplier.set(false);
      },
      error: (err) => {
        this.uploadingSupplier.set(false);
        this.snack.open(err?.error?.detail || 'Failed to preview supplier file', 'OK', { duration: 4000 });
      },
    });
  }

  onWoobeSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.uploadingWoobe.set(true);
    this.api.previewFile(file, 'woobe').subscribe({
      next: (preview) => {
        this.state.setWoobeFile(file, preview);
        this.uploadingWoobe.set(false);
      },
      error: (err) => {
        this.uploadingWoobe.set(false);
        this.snack.open(err?.error?.detail || 'Failed to preview WOOBE file', 'OK', { duration: 4000 });
      },
    });
  }

  clearSupplier() {
    this.state.setSupplierFile(null, null);
  }

  clearWoobe() {
    this.state.setWoobeFile(null, null);
  }

  updateSupplierMapping(col: string, value: string) {
    const mapping = { ...this.state.supplierMapping() };
    if (value) mapping[col] = value;
    else delete mapping[col];
    this.state.setSupplierMapping(mapping);
  }

  updateWoobeMapping(col: string, value: string) {
    const mapping = { ...this.state.woobeMapping() };
    if (value) mapping[col] = value;
    else delete mapping[col];
    this.state.setWoobeMapping(mapping);
  }

  startReconciliation(stepper: any) {
    const supplier = this.state.supplierFile();
    const woobe = this.state.woobeFile();
    if (!supplier || !woobe) return;

    this.starting.set(true);
    this.api
      .startReconciliation(
        supplier,
        woobe,
        this.state.supplierMapping(),
        this.state.woobeMapping()
      )
      .subscribe({
        next: (job) => {
          this.starting.set(false);
          this.state.setCurrentJob(job);
          stepper.next();
          this.pollJob(job.job_id);
        },
        error: (err) => {
          this.starting.set(false);
          this.snack.open(err?.error?.detail || 'Failed to start reconciliation', 'OK', { duration: 5000 });
        },
      });
  }

  private pollJob(jobId: string) {
    this.pollSub?.unsubscribe();
    this.pollSub = interval(1500)
      .pipe(
        switchMap(() => this.api.getJob(jobId)),
        takeWhile((job) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(job.status), true)
      )
      .subscribe({
        next: (job) => {
          this.state.setCurrentJob(job);
          if (job.status === 'COMPLETED') {
            this.api.getJobResults(jobId).subscribe({
              next: (results) => this.state.setResults(results),
            });
          }
        },
      });
  }

  goToResults() {
    const job = this.state.currentJob();
    if (job) {
      this.router.navigate(['/results', job.job_id]);
    }
  }
}
