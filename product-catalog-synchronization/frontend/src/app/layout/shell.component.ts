import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatSidenavModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
  ],
  template: `
    <mat-sidenav-container class="shell">
      <mat-sidenav mode="side" opened class="sidenav">
        <div class="brand">
          <mat-icon>sync_alt</mat-icon>
          <span>PCR Platform</span>
        </div>
        <mat-nav-list>
          <a mat-list-item routerLink="/dashboard" routerLinkActive="active">
            <mat-icon matListItemIcon>dashboard</mat-icon>
            <span matListItemTitle>Dashboard</span>
          </a>
          <a mat-list-item routerLink="/sync" routerLinkActive="active">
            <mat-icon matListItemIcon>upload_file</mat-icon>
            <span matListItemTitle>New Synchronization</span>
          </a>
          <a mat-list-item routerLink="/history" routerLinkActive="active">
            <mat-icon matListItemIcon>history</mat-icon>
            <span matListItemTitle>History</span>
          </a>
          <a mat-list-item routerLink="/settings" routerLinkActive="active">
            <mat-icon matListItemIcon>settings</mat-icon>
            <span matListItemTitle>Settings</span>
          </a>
        </mat-nav-list>
        <div class="sidenav-footer">
          <small>v2.1 · CSV / Excel</small>
        </div>
      </mat-sidenav>

      <mat-sidenav-content>
        <mat-toolbar color="primary" class="topbar">
          <span class="page-title">Product Catalog Reconciliation</span>
          <span class="spacer"></span>
          <span class="badge">WooCommerce / WOOBE</span>
        </mat-toolbar>
        <main class="content">
          <router-outlet />
        </main>
      </mat-sidenav-content>
    </mat-sidenav-container>
  `,
  styles: [
    `
      .shell {
        height: 100vh;
      }
      .sidenav {
        width: 260px;
        background: #0f172a;
        color: #e2e8f0;
        display: flex;
        flex-direction: column;
      }
      .brand {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 20px 16px;
        font-weight: 600;
        font-size: 1.1rem;
        border-bottom: 1px solid #1e293b;
      }
      .brand mat-icon {
        color: #38bdf8;
      }
      mat-nav-list a {
        color: #94a3b8 !important;
        margin: 4px 8px;
        border-radius: 8px;
      }
      mat-nav-list a.active {
        background: #1e293b;
        color: #f8fafc !important;
      }
      mat-nav-list a:hover {
        background: #1e293b;
      }
      .sidenav-footer {
        margin-top: auto;
        padding: 16px;
        color: #64748b;
        font-size: 0.75rem;
      }
      .topbar {
        position: sticky;
        top: 0;
        z-index: 10;
      }
      .page-title {
        font-weight: 500;
      }
      .spacer {
        flex: 1;
      }
      .badge {
        background: rgba(255, 255, 255, 0.15);
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.8rem;
      }
      .content {
        padding: 24px;
        max-width: 1400px;
        margin: 0 auto;
      }
    `,
  ],
})
export class ShellComponent {}
