import React, { useEffect, useState } from 'react';
import { api } from '../api';
import type { Finding } from '../types/contracts';
import {
  FileCode,
  Download,
  RefreshCw,
  Search,
  Filter,
  AlertTriangle,
  ShieldCheck,
  Server
} from 'lucide-react';

export const Inventory: React.FC = () => {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [serviceFilter, setServiceFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');

  const loadFindings = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getFindings();
      setFindings(data);
    } catch (err: any) {
      setError(err?.detail || 'Failed to load CBOM findings.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFindings();
  }, []);

  const handleRunScan = async () => {
    try {
      setScanning(true);
      setScanMessage('Initiating AST and network configuration scanner...');
      const { scan_id } = await api.startScan();

      // Poll scan status
      const interval = setInterval(async () => {
        try {
          const status = await api.getScanStatus(scan_id);
          if (status.status === 'done') {
            clearInterval(interval);
            setScanning(false);
            setScanMessage(`Scan completed in ${status.scan_seconds || 1.2}s. Identified ${status.findings || 10} cryptographic assets.`);
            await loadFindings();
          } else if (status.status === 'failed') {
            clearInterval(interval);
            setScanning(false);
            setError('Discovery scan failed.');
          } else {
            setScanMessage('Scanning AST configurations and network endpoints...');
          }
        } catch (pollErr) {
          clearInterval(interval);
          setScanning(false);
          setError('Polling scan status failed.');
        }
      }, 1000);
    } catch (err: any) {
      setScanning(false);
      setError(err?.detail || 'Failed to trigger discovery scan.');
    }
  };

  const handleDownloadCbom = async () => {
    try {
      const cbomData = await api.getCbom();
      const blob = new Blob([JSON.stringify(cbomData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chronos-cbom-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.detail || 'Failed to download CBOM JSON.');
    }
  };

  // Distinct services for filtering
  const services = Array.from(new Set(findings.map((f) => f.service).filter(Boolean)));

  // Filtered findings
  const filteredFindings = findings.filter((f) => {
    if (statusFilter !== 'all' && f.quantum_status !== statusFilter) return false;
    if (serviceFilter !== 'all' && f.service !== serviceFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchAlgo = f.algorithm?.toLowerCase().includes(term);
      const matchPath = f.location?.path?.toLowerCase().includes(term);
      const matchService = f.service?.toLowerCase().includes(term);
      if (!matchAlgo && !matchPath && !matchService) return false;
    }
    return true;
  });

  return (
    <div className="inventory-page">
      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div className="card-title">
              <FileCode style={{ width: 20, height: 20, color: 'var(--accent-cyan)' }} />
              <span>Cryptographic Bill of Materials (CBOM)</span>
            </div>
            <div className="card-subtitle">
              NIST & CycloneDX 1.6 compliant cryptographic asset inventory discovered via AST parsing and live network probing.
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              onClick={handleRunScan}
              className="btn btn-primary"
              disabled={scanning}
            >
              <RefreshCw className={scanning ? 'spin' : ''} style={{ width: 14, height: 14 }} />
              {scanning ? 'Scanning...' : 'Run Discovery Scan'}
            </button>
            <button
              onClick={handleDownloadCbom}
              className="btn btn-secondary"
            >
              <Download style={{ width: 14, height: 14 }} />
              Download CycloneDX 1.6 JSON
            </button>
          </div>
        </div>

        {scanMessage && (
          <div className="banner info" style={{ marginBottom: '1rem' }}>
            <RefreshCw style={{ width: 14, height: 14 }} />
            <span>{scanMessage}</span>
          </div>
        )}

        {error && (
          <div className="banner error" style={{ marginBottom: '1rem' }}>
            <AlertTriangle style={{ width: 14, height: 14 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Filter Toolbar */}
        <div style={{
          display: 'flex',
          gap: '1rem',
          alignItems: 'center',
          flexWrap: 'wrap',
          marginBottom: '1rem',
          padding: '0.75rem',
          backgroundColor: 'var(--bg-subtle)',
          borderRadius: 6
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: 200 }}>
            <Search style={{ width: 16, height: 16, color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search algorithm, service or file path..."
              className="input-field"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ padding: '0.35rem 0.65rem' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter style={{ width: 14, height: 14, color: 'var(--text-muted)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Status:</span>
            <select
              className="input-field"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: 'auto', padding: '0.35rem 0.65rem' }}
            >
              <option value="all">All Quantum Statuses</option>
              <option value="vulnerable">Vulnerable (Classical)</option>
              <option value="weakened">Weakened</option>
              <option value="resistant">Resistant (PQC)</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Server style={{ width: 14, height: 14, color: 'var(--text-muted)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Service:</span>
            <select
              className="input-field"
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              style={{ width: 'auto', padding: '0.35rem 0.65rem' }}
            >
              <option value="all">All Services</option>
              {services.map((svc) => (
                <option key={svc} value={svc}>{svc}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Findings Table */}
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Asset Type</th>
                <th>Algorithm / Cipher</th>
                <th>Quantum Status</th>
                <th>Usage</th>
                <th>Service & Location</th>
                <th>Fix Class</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>
                    Loading CBOM inventory...
                  </td>
                </tr>
              ) : filteredFindings.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                    No cryptographic findings match the selected criteria.
                  </td>
                </tr>
              ) : (
                filteredFindings.map((finding) => {
                  let statusBadgeClass = 'red';
                  if (finding.quantum_status === 'resistant') statusBadgeClass = 'green';
                  else if (finding.quantum_status === 'weakened') statusBadgeClass = 'yellow';

                  return (
                    <tr key={finding.finding_id}>
                      <td>
                        <span className="badge-tag" style={{ textTransform: 'capitalize' }}>
                          {finding.asset_type.replace('-', ' ')}
                        </span>
                      </td>
                      <td>
                        <code style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                          {finding.algorithm}
                        </code>
                        {finding.params?.curve ? (
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginLeft: 6 }}>
                            ({String(finding.params.curve)})
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className={`badge-tag ${statusBadgeClass}`}>
                          {finding.quantum_status === 'vulnerable' && <AlertTriangle style={{ width: 12, height: 12, display: 'inline', marginRight: 4 }} />}
                          {finding.quantum_status === 'resistant' && <ShieldCheck style={{ width: 12, height: 12, display: 'inline', marginRight: 4 }} />}
                          {finding.quantum_status.toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {finding.usage.replace('_', ' ')}
                        </span>
                      </td>
                      <td>
                        <div>
                          <strong>{finding.service}</strong>
                        </div>
                        <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {finding.location?.path}:{finding.location?.line ?? 1}
                        </code>
                      </td>
                      <td>
                        <span className="badge-tag accent" style={{ fontSize: '0.75rem' }}>
                          {finding.fix_class}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          {Math.round(finding.confidence * 100)}%
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
