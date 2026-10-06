import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ApiService } from '../../core/services/api.service';
import { JobResponse, JobResults, ReconciliationStats } from '../../core/models/reconciliation.models';

@Component({
  selector: 'app-results',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    MatTableModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="results">
      @if (loading()) {
        <div class="loading">
          <mat-spinner></mat-spinner>
          <p>Loading results...</p>
        </div>
      } @else if (error()) {
        <mat-card class="error-card">
          <mat-icon>error</mat-icon>
          <p>{{ error() }}</p>
          <a mat-button routerLink="/dashboard">Back to Dashboard</a>
        </mat-card>
      } @else {
        <div class="header">
          <div>
            <h1>Reconciliation Results</h1>
            <p class="job-id">{{ jobId }}</p>
          </div>
          <div class="header-actions">
            <a mat-stroked-button routerLink="/sync">
              <mat-icon>add</mat-icon>
              New Sync
            </a>
          </div>
        </div>

        <!-- Stats grid -->
        @if (stats(); as s) {
          <div class="stats-grid">
            <mat-card class="stat" style="--c:#3b82f6">
              <div class="num">{{ s.supplier_products | number }}</div>
              <div class="lbl">Supplier Products</div>
            </mat-card>
            <mat-card class="stat" style="--c:#8b5cf6">
              <div class="num">{{ s.woobe_products | number }}</div>
              <div class="lbl">WOOBE Products</div>
            </mat-card>
            <mat-card class="stat" style="--c:#22c55e">
              <div class="num">{{ s.existing | number }}</div>
              <div class="lbl">Matched / Existing</div>
            </mat-card>
            <mat-card class="stat" style="--c:#f59e0b">
              <div class="num">{{ s.price_changed | number }}</div>
              <div class="lbl">Price Changes</div>
            </mat-card>
            <mat-card class="stat" style="--c:#06b6d4">
              <div class="num">{{ s.new_products | number }}</div>
              <div class="lbl">New Products</div>
            </mat-card>
            <mat-card class="stat" style="--c:#ef4444">
              <div class="num">{{ s.potentially_discontinued | number }}</div>
              <div class="lbl">Potentially Discontinued</div>
            </mat-card>
            <mat-card class="stat" style="--c:#a855f7">
              <div class="num">{{ s.duplicate_skus | number }}</div>
              <div class="lbl">Duplicate SKUs</div>
            </mat-card>
            <mat-card class="stat" style="--c:#64748b">
              <div class="num">{{ s.review_required | number }}</div>
              <div class="lbl">Review Required</div>
            </mat-card>
          </div>

          <div class="meta-row">
            <span>Processing time: <strong>{{ s.processing_time_seconds }}s</strong></span>
            <span>Unchanged: <strong>{{ s.unchanged | number }}</strong></span>
            <span>Unmatched: <strong>{{ s.unmatched | number }}</strong></span>
          </div>
        }

        <!-- Downloads -->
        <mat-card class="downloads">
          <h2>Download Reports</h2>
          <div class="dl-grid">
            @for (f of downloadFiles; track f.name) {
              <a mat-stroked-button [href]="downloadUrl(f.name)" target="_blank">
                <mat-icon>download</mat-icon>
                {{ f.label }}
              </a>
            }
          </div>
        </mat-card>

        <!-- Sample matches -->
        @if (results()?.matches_sample?.length) {
          <mat-card class="matches-card">
            <h2>Sample Matches</h2>
            <table mat-table [dataSource]="results()!.matches_sample" class="match-table">
              <ng-container matColumnDef="sku">
                <th mat-header-cell *matHeaderCellDef>SKU</th>
                <td mat-cell *matCellDef="let m">{{ m.supplier_sku || '—' }}</td>
              </ng-container>
              <ng-container matColumnDef="title">
                <th mat-header-cell *matHeaderCellDef>Title</th>
                <td mat-cell *matCellDef="let m">{{ m.supplier_title || '—' }}</td>
              </ng-container>
              <ng-container matColumnDef="match_type">
                <th mat-header-cell *matHeaderCellDef>Match Type</th>
                <td mat-cell *matCellDef="let m">
                  <span class="chip">{{ m.match_type }}</span>
                </td>
              </ng-container>
              <ng-container matColumnDef="confidence">
                <th mat-header-cell *matHeaderCellDef>Confidence</th>
                <td mat-cell *matCellDef="let m">{{ m.confidence | number: '1.0-1' }}%</td>
              </ng-container>
              <ng-container matColumnDef="status">
                <th mat-header-cell *matHeaderCellDef>Status</th>
                <td mat-cell *matCellDef="let m">
                  <span class="status" [attr.data-status]="m.status">{{ m.status }}</span>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
            </table>
          </mat-card>
        }
      }
    </div>
  `,
  styles: [
    `
      .loading, .error-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;
        padding: 64px;
        color: #64748b;
      }
      .header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 24px;
      }
      h1 { margin: 0; font-size: 1.75rem; font-weight: 600; }
      .job-id { font-family: monospace; color: #64748b; margin: 4px 0 0; }
      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
      }
      .stat {
        padding: 16px;
        text-align: center;
        border-top: 3px solid var(--c);
      }
      .stat .num {
        font-size: 1.75rem;
        font-weight: 700;
        color: var(--c);
      }
      .stat .lbl {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 4px;
      }
      .meta-row {
        display: flex;
        gap: 24px;
        margin-bottom: 24px;
        color: #64748b;
        font-size: 0.875rem;
      }
      .downloads, .matches-card {
        padding: 20px;
        margin-bottom: 20px;
      }
      .downloads h2, .matches-card h2 {
        margin: 0 0 16px;
        font-size: 1.1rem;
      }
      .dl-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      .match-table {
        width: 100%;
      }
      .chip {
        background: #e0f2fe;
        color: #0369a1;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 600;
      }
      .status {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 10px;
      }
      .status[data-status="PRICE_CHANGED"] { background: #fef3c7; color: #92400e; }
      .status[data-status="UNCHANGED"] { background: #dcfce7; color: #166534; }
      .status[data-status="NEW"] { background: #dbeafe; color: #1e40af; }
      .status[data-status="DUPLICATE_SKU"] { background: #fce7f3; color: #9d174d; }
      .status[data-status="REVIEW_REQUIRED"] { background: #fef3c7; color: #92400e; }
      .status[data-status="POTENTIALLY_DISCONTINUED"] { background: #fee2e2; color: #991b1b; }
    `,
  ],
})
export class ResultsComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private api = inject(ApiService);
  private snack = inject(MatSnackBar);

  jobId = '';
  loading = signal(true);
  error = signal<string | null>(null);
  job = signal<JobResponse | null>(null);
  results = signal<JobResults | null>(null);
  stats = signal<ReconciliationStats | null>(null);

  displayedColumns = ['sku', 'title', 'match_type', 'confidence', 'status'];

  downloadFiles = [
    { name: 'reconciliation_report.csv', label: 'Full Report' },
    { name: 'woocommerce_updated.csv', label: 'Updated Catalog' },
    { name: 'price_changes.csv', label: 'Price Changes' },
    { name: 'new_products.csv', label: 'New Products' },
    { name: 'potentially_discontinued.csv', label: 'Discontinued' },
    { name: 'duplicate_ids.csv', label: 'Duplicates' },
    { name: 'review_required.csv', label: 'Review Queue' },
    { name: 'reconciliation_stats.json', label: 'Stats (JSON)' },
  ];

  ngOnInit() {
    this.jobId = this.route.snapshot.paramMap.get('jobId') || '';
    if (!this.jobId) {
      this.error.set('No job ID provided');
      this.loading.set(false);
      return;
    }

    this.api.getJob(this.jobId).subscribe({
      next: (job) => {
        this.job.set(job);
        if (job.stats) this.stats.set(job.stats as ReconciliationStats);
        if (job.status === 'COMPLETED') {
          this.api.getJobResults(this.jobId).subscribe({
            next: (res) => {
              this.results.set(res);
              this.stats.set(res.stats);
              this.loading.set(false);
            },
            error: () => this.loading.set(false),
          });
        } else {
          this.loading.set(false);
          if (job.status !== 'COMPLETED') {
            this.error.set(`Job is ${job.status}. Results are only available for completed jobs.`);
          }
        }
      },
      error: () => {
        this.error.set('Job not found');
        this.loading.set(false);
      },
    });
  }

  downloadUrl(fileName: string): string {
    return this.api.getDownloadUrl(this.jobId, fileName);
  }
}
