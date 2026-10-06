import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ApiService } from '../../core/services/api.service';
import { JobSummary } from '../../core/models/reconciliation.models';

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  template: `
    <div class="history">
      <h1>Synchronization History</h1>
      <p class="subtitle">All past reconciliation jobs</p>

      @if (loading()) {
        <div class="loading"><mat-spinner diameter="40"></mat-spinner></div>
      } @else if (jobs().length === 0) {
        <mat-card class="empty">
          <mat-icon>inbox</mat-icon>
          <p>No jobs yet</p>
          <a mat-flat-button color="primary" routerLink="/sync">Start a synchronization</a>
        </mat-card>
      } @else {
        <div class="list">
          @for (job of jobs(); track job.job_id) {
            <mat-card class="job-card">
              <div class="row">
                <div class="id">{{ job.job_id }}</div>
                <span class="status" [attr.data-s]="job.status">{{ job.status }}</span>
              </div>
              <div class="msg">{{ job.message }}</div>
              <div class="footer">
                <span class="date">{{ job.created_at | date: 'medium' }}</span>
                <a mat-button [routerLink]="['/results', job.job_id]"
                   [disabled]="job.status !== 'COMPLETED'">
                  View Results
                </a>
              </div>
            </mat-card>
          }
        </div>
      }
    </div>
  `,
  styles: [
    `
      h1 { margin: 0; font-size: 1.75rem; font-weight: 600; }
      .subtitle { color: #64748b; margin: 4px 0 24px; }
      .loading, .empty {
        display: flex; flex-direction: column; align-items: center;
        gap: 12px; padding: 48px; color: #94a3b8;
      }
      .empty mat-icon { font-size: 48px; width: 48px; height: 48px; }
      .list { display: flex; flex-direction: column; gap: 12px; }
      .job-card { padding: 16px 20px; }
      .row { display: flex; justify-content: space-between; align-items: center; }
      .id { font-family: monospace; font-weight: 600; }
      .status {
        font-size: 0.7rem; font-weight: 700; padding: 2px 10px;
        border-radius: 12px; text-transform: uppercase;
      }
      .status[data-s="COMPLETED"] { background: #dcfce7; color: #166534; }
      .status[data-s="FAILED"] { background: #fee2e2; color: #991b1b; }
      .status[data-s="PENDING"], .status[data-s="MATCHING"] { background: #fef3c7; color: #92400e; }
      .msg { color: #64748b; font-size: 0.875rem; margin: 8px 0; }
      .footer {
        display: flex; justify-content: space-between; align-items: center;
      }
      .date { font-size: 0.8rem; color: #94a3b8; }
    `,
  ],
})
export class HistoryComponent implements OnInit {
  private api = inject(ApiService);
  jobs = signal<JobSummary[]>([]);
  loading = signal(true);

  ngOnInit() {
    this.api.listJobs().subscribe({
      next: (list) => {
        this.jobs.set(list);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}
