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
  selector: 'app-dashboard',
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
    <div class="dashboard">
      <div class="header">
        <div>
          <h1>Dashboard</h1>
          <p class="subtitle">Catalog reconciliation overview</p>
        </div>
        <a mat-flat-button color="primary" routerLink="/sync">
          <mat-icon>add</mat-icon>
          New Synchronization
        </a>
      </div>

      <div class="stats-grid">
        <mat-card class="stat-card">
          <mat-icon class="icon blue">inventory_2</mat-icon>
          <div class="value">{{ totalJobs() }}</div>
          <div class="label">Total Jobs</div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon class="icon green">check_circle</mat-icon>
          <div class="value">{{ completedJobs() }}</div>
          <div class="label">Completed</div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon class="icon amber">hourglass_empty</mat-icon>
          <div class="value">{{ runningJobs() }}</div>
          <div class="label">In Progress</div>
        </mat-card>
        <mat-card class="stat-card">
          <mat-icon class="icon red">error</mat-icon>
          <div class="value">{{ failedJobs() }}</div>
          <div class="label">Failed</div>
        </mat-card>
      </div>

      <mat-card class="recent-card">
        <div class="card-header">
          <h2>Recent Synchronizations</h2>
          <a mat-button routerLink="/history">View all</a>
        </div>

        @if (loading()) {
          <div class="loading">
            <mat-spinner diameter="40"></mat-spinner>
          </div>
        } @else if (jobs().length === 0) {
          <div class="empty">
            <mat-icon>inbox</mat-icon>
            <p>No synchronizations yet</p>
            <a mat-stroked-button color="primary" routerLink="/sync">Start your first sync</a>
          </div>
        } @else {
          <div class="job-list">
            @for (job of jobs(); track job.job_id) {
              <div class="job-row">
                <div class="job-id">{{ job.job_id }}</div>
                <div class="job-status" [class]="job.status.toLowerCase()">
                  {{ job.status }}
                </div>
                <div class="job-msg">{{ job.message }}</div>
                <div class="job-date">{{ job.created_at | date: 'medium' }}</div>
                <a mat-button [routerLink]="['/results', job.job_id]" [disabled]="job.status !== 'COMPLETED'">
                  View
                </a>
              </div>
            }
          </div>
        }
      </mat-card>
    </div>
  `,
  styles: [
    `
      .header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 24px;
      }
      h1 {
        margin: 0;
        font-size: 1.75rem;
        font-weight: 600;
      }
      .subtitle {
        margin: 4px 0 0;
        color: #64748b;
      }
      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
      }
      .stat-card {
        padding: 20px;
        text-align: center;
      }
      .stat-card .icon {
        font-size: 32px;
        width: 32px;
        height: 32px;
      }
      .stat-card .icon.blue { color: #3b82f6; }
      .stat-card .icon.green { color: #22c55e; }
      .stat-card .icon.amber { color: #f59e0b; }
      .stat-card .icon.red { color: #ef4444; }
      .stat-card .value {
        font-size: 2rem;
        font-weight: 700;
        margin: 8px 0 4px;
      }
      .stat-card .label {
        color: #64748b;
        font-size: 0.875rem;
      }
      .recent-card {
        padding: 20px;
      }
      .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
      }
      .card-header h2 {
        margin: 0;
        font-size: 1.15rem;
      }
      .loading, .empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;
        padding: 48px;
        color: #94a3b8;
      }
      .empty mat-icon {
        font-size: 48px;
        width: 48px;
        height: 48px;
      }
      .job-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .job-row {
        display: grid;
        grid-template-columns: 180px 110px 1fr 160px 80px;
        gap: 12px;
        align-items: center;
        padding: 12px;
        border-radius: 8px;
        background: #f8fafc;
        font-size: 0.875rem;
      }
      .job-id {
        font-family: monospace;
        font-weight: 500;
      }
      .job-status {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 12px;
        text-align: center;
        text-transform: uppercase;
      }
      .job-status.completed { background: #dcfce7; color: #166534; }
      .job-status.failed { background: #fee2e2; color: #991b1b; }
      .job-status.pending, .job-status.matching { background: #fef3c7; color: #92400e; }
      .job-msg {
        color: #64748b;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .job-date {
        color: #94a3b8;
        font-size: 0.8rem;
      }
    `,
  ],
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);

  jobs = signal<JobSummary[]>([]);
  loading = signal(true);

  totalJobs = signal(0);
  completedJobs = signal(0);
  runningJobs = signal(0);
  failedJobs = signal(0);

  ngOnInit() {
    this.api.listJobs().subscribe({
      next: (list) => {
        this.jobs.set(list.slice(0, 8));
        this.totalJobs.set(list.length);
        this.completedJobs.set(list.filter((j) => j.status === 'COMPLETED').length);
        this.runningJobs.set(
          list.filter((j) => !['COMPLETED', 'FAILED', 'CANCELLED'].includes(j.status)).length
        );
        this.failedJobs.set(list.filter((j) => j.status === 'FAILED').length);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}
