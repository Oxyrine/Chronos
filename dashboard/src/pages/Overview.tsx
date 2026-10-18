import React, { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import type { ExposureResponse, SystemHealth } from '../types/contracts';
import { ShieldAlert, AlertTriangle, Sliders, Calendar, ArrowRight, Database } from 'lucide-react';

type ExposureRow = ExposureResponse['exposures'][number];

// Every number on this page comes from GET /api/metrics, GET /api/exposure or GET /health.
// When a value is missing it is shown as "not measured", never replaced by a constant.
const NOT_MEASURED = 'not measured';

const pct = (v: unknown, digits = 1) => (typeof v === 'number' ? `${(v * 100).toFixed(digits)}%` : NOT_MEASURED);
const num = (v: unknown) => (typeof v === 'number' ? Math.round(v).toLocaleString() : NOT_MEASURED);
const signed = (v: number) => (v > 0 ? `+${v}` : `${v}`);

const DEADLINES = [
  { date: '2026-12-31', label: 'EU roadmap: national PQC strategies and first steps', source: 'EU Coordinated Roadmap (June 2025)' },
  { date: '2030-12-31', label: 'EU roadmap: high-risk use cases (incl. health) migrated', source: 'EU Coordinated Roadmap (June 2025)' },
];

const daysUntil = (iso: string) => Math.ceil((new Date(`${iso}T23:59:59Z`).getTime() - Date.now()) / 86_400_000);

function verdict(row: ExposureRow) {
  if (row.exposed) return <span className="badge-tag red">EXPOSED (M &gt; 0, classical sessions)</span>;
  if (row.margin > 0) return <span className="badge-tag yellow">M &gt; 0, no classical sessions measured</span>;
  return <span className="badge-tag green">Not urgent (M &le; 0)</span>;
}

const TwinCard: React.FC<{ title: string; row?: ExposureRow; accent: string }> = ({ title, row, accent }) => (
  <div className="card" style={{ borderLeft: `3px solid ${accent}` }}>
    <div className="card-header">
      <div className="card-title" style={{ color: accent }}>
        <ShieldAlert style={{ width: 18, height: 18 }} />
        <span>{title}</span>
      </div>
      {row && <span className={`badge-tag ${row.exposed ? 'red' : 'green'}`}>M = {signed(row.margin)} years</span>}
    </div>
    {row ? (
      <div style={{ backgroundColor: 'var(--bg-subtle)', padding: '0.75rem', borderRadius: 6, fontSize: '0.85rem', lineHeight: 1.6 }}>
        <div>Table <code>{row.store_table}</code> over <code>{row.channel}</code></div>
        <div>Driving column: <code>{String(row.driving_column ?? 'unknown')}</code> → shelf-life X = <strong>{row.x_years} years</strong></div>
        <div>M = X + Y − Z = {row.x_years} + {row.y_years} − {row.z_years} = <strong>{signed(row.margin)} years</strong></div>
        <div>Priority: <strong>{row.priority}</strong> / 100 · classical share {(row.classical_share * 100).toFixed(0)}%</div>
      </div>
    ) : (
      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No exposure row for this table yet. Run a scan and a classification.</p>
    )}
  </div>
);

export const Overview: React.FC = () => {
  const [scenario, setScenario] = useState<string>('base_2033');
  const [crqcYear, setCrqcYear] = useState<number>(2033);
  const [exposureData, setExposureData] = useState<ExposureResponse | null>(null);
  const [needsRun, setNeedsRun] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getMetrics().then(setMetrics).catch(() => setMetrics(null));
    api.getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getExposure(scenario)
      .then((exp) => { setExposureData(exp); setNeedsRun(null); })
      .catch((err) => {
        setExposureData(null);
        if (err instanceof ApiError && err.status === 409) setNeedsRun(err.detail);
        else setError(err?.detail || 'Failed to load exposure data.');
      })
      .finally(() => setLoading(false));
  }, [scenario]);

  const choose = (name: string, year: number) => { setScenario(name); setCrqcYear(year); };
  const onSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    const yr = parseInt(e.target.value, 10);
    choose(`custom_${yr}`, yr);
  };

  const exposureM = metrics?.exposure ?? {};
  const discovery = metrics?.discovery ?? {};
  const heldOut = metrics?.shelflife?.fixed_split?.test ?? {};
  const mix = exposureM.client_mix;
  const openRoutes: unknown[] = Array.isArray(exposureM.classical_routes_still_open) ? exposureM.classical_routes_still_open : [];
  const rows = exposureData?.exposures ?? [];
  const exposedCount = rows.filter((r) => r.exposed).length;
  const portal = rows.find((r) => r.channel === 'internet->portal' && r.store_table === 'patients');
  const reminders = rows.find((r) => r.channel === 'internet->reminders' && r.store_table === 'appointment_reminders');
  const zYears = rows[0]?.z_years;

  return (
    <div className="overview-page">
      <div className="card" style={{ borderLeft: '4px solid var(--accent-cyan)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
          <span className="badge-tag accent">Theme 2: AI Secured</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Discover → Prioritize → Fix → Sign</span>
        </div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          &ldquo;Chronos understands sensitive data without exporting it, then protects how it travels from here on.&rdquo;
        </h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.35rem' }}>
          St. Aster General is a fictional hospital. All data on this page is synthetic.
        </p>
      </div>

      {error && (
        <div className="banner error"><AlertTriangle style={{ width: 16, height: 16 }} /><span>{error}</span></div>
      )}

      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="metric-box">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div className="metric-label">Future-transfer exposure (E)</div>
            <span className="provenance-tag">GET /api/metrics</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
            <span className="metric-value" style={{ color: 'var(--accent-red)' }}>{num(exposureM.E_before)}</span>
            <ArrowRight style={{ width: 16, height: 16, color: 'var(--text-muted)' }} />
            <span className="metric-value" style={{ color: 'var(--accent-green)' }}>{num(exposureM.E_after)}</span>
          </div>
          <div className="metric-diff positive">
            {typeof exposureM.drop === 'number' ? `↓ ${pct(exposureM.drop)} after the verified fixes` : NOT_MEASURED}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            An index, not a count of captured records.
            {mix ? ` Client mix ${mix.hybrid_capable}/${mix.legacy} (hybrid-capable/legacy).` : ''}
            {` ${openRoutes.length} classical route(s) still open.`}
            {exposureData ? ` Live now (${scenario}): E = ${num(exposureData.E)}.` : ''}
          </div>
        </div>

        <div className="metric-box">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div className="metric-label">Discovery recall</div>
            <span className="provenance-tag">GET /api/metrics</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-cyan)' }}>
            {pct(discovery.recall)}
            {typeof discovery.current_scan?.recall === 'number' && (
              <span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}> → {pct(discovery.current_scan.recall)}</span>
            )}
          </div>
          <div className="metric-diff positive">
            {typeof discovery.ground_truth === 'number' ? `${discovery.ground_truth} planted assets; precision ${pct(discovery.precision)}` : NOT_MEASURED}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            First value is the measurement; the second is after closing the known gaps (tuned, not independent).
          </div>
        </div>

        <div className="metric-box">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div className="metric-label">Classifier macro-F1 (held-out)</div>
            <span className="provenance-tag">GET /api/metrics</span>
          </div>
          <div className="metric-value" style={{ color: 'var(--accent-yellow)' }}>{pct(heldOut.macro_f1)}</div>
          <div className="metric-diff">Under-protection {pct(heldOut.under_protection_rate)}</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            Synthetic School domain; agreement with our labels, not legal accuracy. Backend: {metrics?.shelflife?.backend ?? NOT_MEASURED}.
          </div>
        </div>

        <div className="metric-box">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div className="metric-label">Platform</div>
            <span className="provenance-tag">GET /health</span>
          </div>
          <div className="metric-value" style={{ fontSize: '1.5rem', color: 'var(--accent-purple)' }}>{health?.arch ?? NOT_MEASURED}</div>
          <div className="metric-diff" style={{ color: 'var(--text-secondary)' }}>
            NNPA accelerator: {health ? (health.nnpa ? 'detected' : 'not present') : NOT_MEASURED}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            {health?.arch === 's390x' ? 'Running on IBM LinuxONE.' : 'Not the LinuxONE VM: numbers above were measured there.'}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Sliders style={{ width: 18, height: 18, color: 'var(--accent-cyan)' }} />
              <span>When could a quantum computer break today's key exchange?</span>
            </div>
            <div className="card-subtitle">Planning scenarios, not predictions. Moving the year recomputes every margin.</div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {([['early_2030', 2030, 'Early (2030)'], ['base_2033', 2033, 'Base (2033)'], ['late_2035', 2035, 'Late (2035)']] as const).map(([name, yr, label]) => (
              <button key={name} onClick={() => choose(name, yr)}
                className={`btn ${scenario === name ? 'btn-primary' : 'btn-secondary'}`} style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                {label}
              </button>
            ))}
          </div>
        </div>
        <div style={{ padding: '0.5rem 0 1rem 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.875rem' }}>
            <label htmlFor="crqc-year">Custom year: <strong style={{ color: 'var(--accent-cyan)' }}>{crqcYear}</strong></label>
            <span style={{ color: 'var(--text-muted)' }}>2028 – 2040</span>
          </div>
          <input id="crqc-year" type="range" min="2028" max="2040" value={crqcYear} onChange={onSlider}
            style={{ width: '100%', accentColor: 'var(--accent-cyan)', cursor: 'pointer' }} />
        </div>
        <div style={{ backgroundColor: 'var(--bg-subtle)', padding: '0.85rem 1.25rem', borderRadius: 6, border: '1px solid var(--border-color)', fontSize: '0.85rem' }}>
          <strong>Mosca&rsquo;s rule:</strong> <code style={{ color: 'var(--accent-cyan)' }}>M = X + Y − Z</code>, where X = years the data must stay secret,
          Y = years to migrate (by fix type), Z = years until a quantum computer{typeof zYears === 'number' ? ` (${zYears} in this scenario)` : ''}.
          {' '}M &gt; 0 means migration is urgent under this scenario, not that data was captured.
          {exposureData && <> {' '}<strong>{exposedCount}</strong> of {rows.length} channel/table pairs are exposed.</>}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">
              <Database style={{ width: 18, height: 18, color: 'var(--accent-cyan)' }} />
              <span>Mosca margins by channel and table</span>
            </div>
            <div className="card-subtitle">Exposed = M &gt; 0 and some sessions on the channel still negotiate a classical key exchange.</div>
          </div>
          <span className="provenance-tag">GET /api/exposure?scenario={scenario}</span>
        </div>
        <div className="heatmap-container">
          {needsRun ? (
            <div className="banner info"><AlertTriangle style={{ width: 16, height: 16 }} /><span>{needsRun}</span></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Channel</th><th>Table</th><th>Driving column</th><th>X</th><th>Y</th><th>Z</th><th>M</th><th>Classical share</th><th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>Computing margins for {scenario}…</td></tr>
                ) : rows.length === 0 ? (
                  <tr><td colSpan={9} style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)' }}>No exposure rows.</td></tr>
                ) : rows.map((r) => (
                  <tr key={`${r.channel}|${r.store_table}`} style={{ backgroundColor: r.exposed ? 'rgba(239, 68, 68, 0.04)' : undefined }}>
                    <td><strong>{r.channel}</strong></td>
                    <td><code>{r.store_table}</code></td>
                    <td><code>{String(r.driving_column ?? 'unknown')}</code></td>
                    <td>{r.x_years}y</td><td>{r.y_years}y</td><td>{r.z_years}y</td>
                    <td><strong style={{ color: r.margin > 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>{signed(r.margin)}y</strong></td>
                    <td>{(r.classical_share * 100).toFixed(0)}%</td>
                    <td>{verdict(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <h3 style={{ fontSize: '1rem', margin: '0 0 0.75rem 0' }}>Same crypto, different data, different urgency</h3>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
        The portal and the reminders service run the same nginx TLS configuration. Only the data they carry differs.
      </p>
      <div className="grid-2" style={{ marginBottom: '1.5rem' }}>
        <TwinCard title="Patient portal" row={portal} accent="var(--accent-red)" />
        <TwinCard title="Appointment reminders" row={reminders} accent="var(--accent-yellow)" />
      </div>

      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Calendar style={{ width: 18, height: 18, color: 'var(--accent-yellow)' }} />
            <span>Deadlines</span>
          </div>
        </div>
        <div className="grid-3">
          {DEADLINES.map((d) => (
            <div key={d.date} style={{ backgroundColor: 'var(--bg-subtle)', padding: '1rem', borderRadius: 6 }}>
              <div style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{daysUntil(d.date).toLocaleString()} days</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>until {d.date}: {d.label}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{d.source}</div>
            </div>
          ))}
          <div style={{ backgroundColor: 'var(--bg-subtle)', padding: '1rem', borderRadius: 6 }}>
            <div style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>NIST IR 8547 (draft)</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.25rem 0' }}>
              Proposed: RSA-2048 and P-256 deprecated after 2030; quantum-vulnerable public-key algorithms disallowed after 2035 for systems following NIST standards.
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>A draft proposal, not a universal legal ban.</div>
          </div>
        </div>
      </div>
    </div>
  );
};
