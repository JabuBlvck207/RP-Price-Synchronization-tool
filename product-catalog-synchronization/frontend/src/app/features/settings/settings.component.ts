import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSliderModule } from '@angular/material/slider';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSliderModule,
  ],
  template: `
    <div class="settings">
      <h1>Settings</h1>
      <p class="subtitle">Matching and processing configuration</p>

      <mat-card class="card">
        <h2>Matching Thresholds</h2>
        <p class="hint">These values control when fuzzy matches are auto-accepted or sent to review.</p>

        <div class="field">
          <label>Fuzzy match threshold (default 85)</label>
          <mat-slider min="50" max="100" step="1" discrete>
            <input matSliderThumb [(ngModel)]="fuzzyThreshold" />
          </mat-slider>
          <span class="val">{{ fuzzyThreshold }}</span>
        </div>

        <div class="field">
          <label>Auto-match minimum score (default 85)</label>
          <mat-slider min="50" max="100" step="1" discrete>
            <input matSliderThumb [(ngModel)]="autoMatchMin" />
          </mat-slider>
          <span class="val">{{ autoMatchMin }}</span>
        </div>
      </mat-card>

      <mat-card class="card">
        <h2>About</h2>
        <p><strong>Product Catalog Reconciliation Platform</strong></p>
        <p>Version 2.1 · CSV / Excel support</p>
        <p>Primary use case: Supplier Price List → WooCommerce / WOOBE</p>
        <p class="hint">PDF support and advanced settings will be available in a later release.</p>
      </mat-card>
    </div>
  `,
  styles: [
    `
      h1 { margin: 0; font-size: 1.75rem; font-weight: 600; }
      .subtitle { color: #64748b; margin: 4px 0 24px; }
      .card { padding: 24px; margin-bottom: 20px; max-width: 560px; }
      .card h2 { margin: 0 0 8px; font-size: 1.1rem; }
      .hint { color: #94a3b8; font-size: 0.875rem; margin: 0 0 16px; }
      .field {
        display: grid;
        grid-template-columns: 1fr auto;
        align-items: center;
        gap: 8px 16px;
        margin-bottom: 16px;
      }
      .field label { grid-column: 1 / -1; font-size: 0.875rem; color: #475569; }
      .val { font-weight: 600; min-width: 32px; text-align: right; }
    `,
  ],
})
export class SettingsComponent {
  fuzzyThreshold = 85;
  autoMatchMin = 85;
}
