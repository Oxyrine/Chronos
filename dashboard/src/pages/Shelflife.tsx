import React, { useEffect, useState } from 'react';
import { api } from '../api';
import type { ShelflifePrediction, UserSession } from '../types/contracts';
import {
  Lock,
  Database,
  RefreshCw,
  Edit3,
  AlertCircle,
  CheckCircle2,
  XCircle,
  HelpCircle
} from 'lucide-react';

interface ShelflifeProps {
  user: UserSession | null;
}

const CATEGORIES = [
  { value: 'genetic', label: 'Genetic / Biometric (50y)' },
  { value: 'child_health', label: 'Child Health (25y)' },
  { value: 'clinical', label: 'Clinical Medical Records (25y)' },
  { value: 'identity', label: 'Government Identity (20y)' },
  { value: 'financial', label: 'Financial Records (10y)' },
  { value: 'contact', label: 'Contact Information (7y)' },
  { value: 'pseudonymous_id', label: 'Pseudonymous Identifier (10y)' },
  { value: 'scheduling', label: 'Scheduling & Appointments (3y)' },
  { value: 'auth_secret', label: 'Authentication Secrets (5y)' },
  { value: 'non_sensitive', label: 'Non-Sensitive / Public (0y)' },
];

export const Shelflife: React.FC<ShelflifeProps> = ({ user }) => {
  const [predictions, setPredictions] = useState<ShelflifePrediction[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Override modal state
  const [activeOverride, setActiveOverride] = useState<ShelflifePrediction | null>(null);
  const [newCategory, setNewCategory] = useState<string>('clinical');
  const [overrideReason, setOverrideReason] = useState<string>('');
  const [overrideSubmitting, setOverrideSubmitting] = useState<boolean>(false);
  const [overrideError, setOverrideError] = useState<string | null>(null);

  const isSecops = user?.role === 'security_engineer';

  const loadPredictions = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getShelflife();
      setPredictions(data);
    } catch (err: any) {
      setError(err?.detail || 'Failed to load shelf-life predictions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPredictions();
  }, []);

  const handleRunShelflife = async () => {
    try {
      setRunning(true);
      setRunMessage('Profiling columns inside the database and classifying them with the Snap ML model...');
      const res = await api.runShelflife();
      setRunMessage(`Classification complete for ${res.columns || predictions.length} columns.`);
      await loadPredictions();
    } catch (err: any) {
      setError(err?.detail || 'In-DB shelf-life classification failed.');
    } finally {
      setRunning(false);
    }
  };

  const openOverrideModal = (pred: ShelflifePrediction) => {
    setActiveOverride(pred);
    setNewCategory(pred.category);
    setOverrideReason('');
    setOverrideError(null);
  };

  const handleOverrideSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOverride) return;
    if (!overrideReason.trim()) {
      setOverrideError('An audit justification reason is strictly required for compliance logging.');
      return;
    }

    try {
      setOverrideSubmitting(true);
      setOverrideError(null);
      await api.overrideShelflife(activeOverride.table, activeOverride.column, newCategory, overrideReason.trim());
      setActiveOverride(null);
      await loadPredictions();
    } catch (err: any) {
      setOverrideError(err?.detail || 'Failed to submit classification override.');
    } finally {
      setOverrideSubmitting(false);
    }
  };

  return (
    <div className="shelflife-page">
      {/* Zero Data Egress Privacy Banner */}
      <div className="banner info" style={{ padding: '1rem', borderLeft: '4px solid var(--accent-cyan)' }}>
        <Lock style={{ width: 22, height: 22, flexShrink: 0, color: 'var(--accent-cyan)' }} />
        <div>
          <strong style={{ fontSize: '0.95rem' }}>Data minimisation:</strong>{' '}
          No raw cell value leaves the database. Profiling runs inside the database container and returns only aggregates (pattern hit rates, value length, uniqueness, null ratio); the Snap ML gradient-boosting model sees those plus column and table names.
        </div>
      </div>

      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div className="card-title">
              <Database style={{ width: 20, height: 20, color: 'var(--accent-cyan)' }} />
              <span>In-DB Column Sensitivity & Shelf-Life Profiling</span>
            </div>
            <div className="card-subtitle">
              Calculates Mosca data shelf-life (X) by mapping database columns to retention policies.
            </div>
          </div>

          <button
            onClick={handleRunShelflife}
            className="btn btn-primary"
            disabled={running}
          >
            <RefreshCw className={running ? 'spin' : ''} style={{ width: 14, height: 14 }} />
            {running ? 'Running in-DB classifier...' : 'Run In-DB Classification'}
          </button>
        </div>

        {runMessage && (
          <div className="banner info" style={{ marginBottom: '1rem' }}>
            <CheckCircle2 style={{ width: 16, height: 16 }} />
            <span>{runMessage}</span>
          </div>
        )}

        {error && (
          <div className="banner error" style={{ marginBottom: '1rem' }}>
            <AlertCircle style={{ width: 16, height: 16 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Driving Column Roll-Up Explanation Box */}
        <div style={{
          backgroundColor: 'var(--bg-subtle)',
          border: '1px solid var(--border-color)',
          borderRadius: 6,
          padding: '0.75rem 1rem',
          marginBottom: '1.25rem',
          fontSize: '0.85rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
            <HelpCircle style={{ width: 16, height: 16 }} />
            Table-Level Mosca Roll-Up Logic:
          </div>
          <p style={{ marginTop: '0.25rem', color: 'var(--text-secondary)' }}>
            A channel&rsquo;s data shelf-life is governed by the highest retention requirement among its transmitted columns:
            {' '}<code style={{ color: 'var(--text-primary)' }}>X_table = max(X_columns)</code>. For instance, the <code>patients</code> table contains <code>patient_id</code> (10y) and <code>blood_group</code> (50y); the entire channel is therefore scored with <strong>X = 50 years</strong>.
          </p>
        </div>

        {/* Profiling Predictions Table */}
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Table & Column</th>
                <th>Predicted Category</th>
                <th>Retention (X)</th>
                <th>Confidence & Top Features</th>
                <th>Decided By</th>
                <th>Audit Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                    Loading column sensitivity predictions...
                  </td>
                </tr>
              ) : predictions.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                    No predictions found. Click &ldquo;Run In-DB Classification&rdquo; to profile database schemas.
                  </td>
                </tr>
              ) : (
                predictions.map((pred, idx) => {
                  const isHighRisk = pred.policy_years >= 25;
                  const isOverridden = pred.decided_by === 'override';

                  return (
                    <tr key={`${pred.table}-${pred.column}-${idx}`}>
                      <td>
                        <strong>{pred.table}</strong>.<code>{pred.column}</code>
                        {pred.store && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            Store: {pred.store}
                          </div>
                        )}
                      </td>
                      <td>
                        <span className={`badge-tag ${isHighRisk ? 'red' : 'accent'}`} style={{ textTransform: 'capitalize' }}>
                          {pred.category.replace('_', ' ')}
                        </span>
                      </td>
                      <td>
                        <strong style={{ color: isHighRisk ? 'var(--accent-red)' : 'var(--text-primary)' }}>
                          {pred.policy_years} years
                        </strong>
                      </td>
                      <td>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          {pred.top_features && pred.top_features.length > 0 ? (
                            <span>{pred.top_features.slice(0, 3).join(', ')}</span>
                          ) : (
                            <span>no strong value pattern</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className={`badge-tag ${isOverridden ? 'yellow' : 'accent'}`} style={{ fontSize: '0.75rem' }}>
                          {pred.decided_by}
                        </span>
                      </td>
                      <td>
                        {isSecops ? (
                          <button
                            onClick={() => openOverrideModal(pred)}
                            className="btn btn-secondary"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                          >
                            <Edit3 style={{ width: 12, height: 12 }} />
                            Override
                          </button>
                        ) : (
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            secops only
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Manual Override Modal */}
      {activeOverride && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>
                Override Sensitivity Classification
              </h3>
              <button
                onClick={() => setActiveOverride(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <XCircle style={{ width: 20, height: 20 }} />
              </button>
            </div>

            {overrideError && (
              <div className="banner error" style={{ marginBottom: '1rem' }}>
                <AlertCircle style={{ width: 16, height: 16 }} />
                <span>{overrideError}</span>
              </div>
            )}

            <form onSubmit={handleOverrideSubmit}>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Target Target: <code>{activeOverride.table}.{activeOverride.column}</code>
                </label>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Select Regulatory Category:
                </label>
                <select
                  className="input-field"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  disabled={overrideSubmitting}
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.35rem' }}>
                  Audit Justification Reason (Required):
                </label>
                <textarea
                  className="input-field"
                  rows={3}
                  placeholder="e.g. Verified by Hospital Compliance Board: contains raw HLA genomic sequencing data requiring 50-year statutory retention."
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  disabled={overrideSubmitting}
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={() => setActiveOverride(null)}
                  className="btn btn-secondary"
                  disabled={overrideSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={overrideSubmitting}
                >
                  {overrideSubmitting ? 'Logging Override...' : 'Confirm & Log Override'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
