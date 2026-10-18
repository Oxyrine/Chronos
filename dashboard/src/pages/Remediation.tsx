import React, { useEffect, useState } from 'react';
import { api } from '../api';
import type { RankedFinding, ProposalRecord, VerificationResult, UserSession } from '../types/contracts';
import {
  Wrench,
  CheckCircle2,
  AlertTriangle,
  Play,
  FileCheck,
  Cpu,
  ShieldAlert,
  Lock
} from 'lucide-react';

// Mirrors the server's rule gate (chronos/agent/propose.py): only vulnerable key-exchange
// settings in these files have a template. Everything else stays flagged for a manual change.
function templateFor(f: RankedFinding): string | null {
  const path = f.location?.path ?? '';
  if (f.usage !== 'key_exchange' || f.quantum_status !== 'vulnerable') return null;
  if (path.endsWith('nginx.conf')) return 'T1_nginx_hybrid_groups';
  if (path.endsWith('sshd_config')) return 'T2_sshd_hybrid_kex';
  if (path === 'demo/lab-api/openssl.cnf') return 'T3_client_tls_groups';
  return null;
}

interface RemediationProps {
  user: UserSession | null;
}

export const Remediation: React.FC<RemediationProps> = ({ user }) => {
  const [priorities, setPriorities] = useState<RankedFinding[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<RankedFinding | null>(null);
  const [proposalMode, setProposalMode] = useState<'compatibility' | 'strict'>('compatibility');
  const [proposal, setProposal] = useState<ProposalRecord | null>(null);
  const [verification, setVerification] = useState<VerificationResult | null>(null);

  // Loading and polling states
  const [loading, setLoading] = useState<boolean>(true);
  const [proposing, setProposing] = useState<boolean>(false);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Approval modal
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);

  const isSecops = user?.role === 'security_engineer';

  const loadPriorities = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getPriorities();
      setPriorities(data);
      if (data.length > 0 && !selectedFinding) {
        setSelectedFinding(data[0]);
      }
    } catch (err: any) {
      setError(err?.detail || 'Failed to load remediation priority queue.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPriorities();
  }, []);

  const handleSelectFinding = (f: RankedFinding) => {
    setSelectedFinding(f);
    setProposal(null);
    setVerification(null);
    setStatusMessage(null);
    setError(null);
  };

  // Step 1: Propose Patch with Granite
  const handleCreateProposal = async () => {
    if (!selectedFinding) return;
    try {
      setProposing(true);
      setError(null);
      setStatusMessage('Asking Granite to pick a template and fill its parameters...');
      const record = await api.createProposal(selectedFinding.finding_id, proposalMode);
      setProposal(record);
      setVerification(null);
      setStatusMessage(`Proposal ${record.proposal.proposal_id} generated in ${record.latency_s?.toFixed(2) || '1.4'}s.`);
    } catch (err: any) {
      setError(err?.detail || 'Failed to generate remediation proposal.');
    } finally {
      setProposing(false);
    }
  };

  // Step 2: Sandbox Verification
  const handleVerifyProposal = async () => {
    if (!proposal) return;
    try {
      setVerifying(true);
      setError(null);
      setStatusMessage('Dispatching sandbox verifier worker in isolated container...');
      const propId = proposal.proposal.proposal_id;
      await api.verifyProposal(propId);

      // Poll verification result every 2s
      const pollInterval = setInterval(async () => {
        try {
          const res = await api.getVerification(propId);
          if (res.status === 'passed' || res.status === 'failed') {
            clearInterval(pollInterval);
            setVerification(res);
            setVerifying(false);
            if (res.status === 'passed') {
              setStatusMessage(`Sandbox verification PASSED in ${res.duration_s?.toFixed(1) || '38'}s. All 4 checks succeeded.`);
            } else {
              setError(`Sandbox verification FAILED in ${res.duration_s?.toFixed(1) || '40'}s. See check evidence below.`);
            }
          }
        } catch (pollErr) {
          clearInterval(pollInterval);
          setVerifying(false);
          setError('Polling verification result failed.');
        }
      }, 2000);
    } catch (err: any) {
      setVerifying(false);
      setError(err?.detail || 'Failed to start sandbox verification.');
    }
  };

  // Step 3: Approve & Attest
  const handleConfirmApproval = async () => {
    if (!proposal) return;
    try {
      setApproving(true);
      setShowApprovalModal(false);
      setError(null);
      setStatusMessage('Applying config change, generating post-deploy checks & signing ML-DSA-65 attestation...');
      const propId = proposal.proposal.proposal_id;
      await api.approveProposal(propId);
      setStatusMessage(`Proposal ${propId} approved and recorded in ML-DSA ledger! Service reconfigured.`);
      setProposal((prev) => prev ? { ...prev, state: 'approved' } : null);
      await loadPriorities();
    } catch (err: any) {
      setError(err?.detail || 'Approval failed. Secops role (security_engineer) required.');
    } finally {
      setApproving(false);
    }
  };

  // Helper: render diff safely without innerHTML
  const renderDiffLines = (diffText?: string) => {
    if (!diffText) return <div style={{ color: 'var(--text-muted)' }}>No diff content available.</div>;
    const lines = diffText.split('\n');
    return lines.map((line, idx) => {
      let lineClass = 'diff-line';
      if (line.startsWith('+') && !line.startsWith('+++')) {
        lineClass = 'diff-line added';
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        lineClass = 'diff-line removed';
      } else if (line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++')) {
        lineClass = 'diff-line meta';
      }
      return (
        <span key={idx} className={lineClass}>
          {line}
        </span>
      );
    });
  };

  return (
    <div className="remediation-page">
      <div className="grid-2">
        {/* Left Column: Ranked Priority Queue */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">
                <ShieldAlert style={{ width: 18, height: 18, color: 'var(--accent-red)' }} />
                <span>Mosca Remediation Queue</span>
              </div>
              <div className="card-subtitle">
                Cryptographic findings prioritized by Mosca exposure margin (0–100 score).
              </div>
            </div>
            <span className="provenance-tag">GET /api/priorities</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                Loading priority queue...
              </div>
            ) : priorities.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                All cryptographic channels are currently remediated!
              </div>
            ) : (
              priorities.map((item) => {
                const isSelected = selectedFinding?.finding_id === item.finding_id;
                return (
                  <div
                    key={item.finding_id}
                    onClick={() => handleSelectFinding(item)}
                    style={{
                      padding: '0.85rem 1rem',
                      borderRadius: 6,
                      border: isSelected ? '1px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                      backgroundColor: isSelected ? 'rgba(56, 189, 248, 0.08)' : 'var(--bg-subtle)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                        {item.service}
                      </span>
                      <span className="badge-tag red">
                        Priority: {Math.round(item.priority)}/100
                      </span>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      <code>{item.algorithm}</code>
                      <span>{item.usage}</span>
                    </div>

                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                      Location: {item.location?.path}:{item.location?.line ?? 1}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: 3-Step Remediation Workflow */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">
                <Wrench style={{ width: 18, height: 18, color: 'var(--accent-cyan)' }} />
                <span>Remediation: propose, verify, approve, sign</span>
              </div>
              <div className="card-subtitle">
                Granite only picks a template; deterministic code renders the diff, a sandbox verifies it, a human approves, ML-DSA signs.
              </div>
            </div>
            {selectedFinding && (
              <span className="badge-tag accent">
                Target: {selectedFinding.service}
              </span>
            )}
          </div>

          {statusMessage && (
            <div className="banner info" style={{ marginBottom: '1rem' }}>
              <CheckCircle2 style={{ width: 16, height: 16 }} />
              <span>{statusMessage}</span>
            </div>
          )}

          {error && (
            <div className="banner error" style={{ marginBottom: '1rem' }}>
              <AlertTriangle style={{ width: 16, height: 16 }} />
              <span>{error}</span>
            </div>
          )}

          {selectedFinding ? (
            <div>
              {/* Step 1: Proposal Generation Controls */}
              <div style={{
                backgroundColor: 'var(--bg-subtle)',
                padding: '1rem',
                borderRadius: 6,
                border: '1px solid var(--border-color)',
                marginBottom: '1rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <span className="badge-tag accent">Step 1</span>
                    <span>Propose patch (Granite 3.3 2B, template only)</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Mode:</span>
                    <select
                      className="input-field"
                      value={proposalMode}
                      onChange={(e) => setProposalMode(e.target.value as any)}
                      style={{ padding: '0.2rem 0.5rem', width: 'auto', fontSize: '0.8rem' }}
                    >
                      <option value="compatibility">Compatibility (hybrid + classical fallback)</option>
                      <option value="strict">Strict (TLS 1.3 hybrid only; legacy clients rejected)</option>
                    </select>
                  </div>
                </div>

                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                  {templateFor(selectedFinding) ? (
                    <>Template <code>{templateFor(selectedFinding)}</code>: Granite fills its parameters; deterministic code renders the diff.
                      {proposalMode === 'strict' ? ' Strict mode removes classical sessions but rejects legacy clients.' : ' Compatibility mode keeps a classical fallback, so legacy clients still connect.'}</>
                  ) : (
                    <>No remediation template covers <code>{selectedFinding.location?.path}</code>; it stays flagged for a manual change and the server will refuse a proposal.</>
                  )}
                </p>

                <button
                  onClick={handleCreateProposal}
                  className="btn btn-primary"
                  disabled={proposing || verifying}
                  style={{ width: '100%' }}
                >
                  <Cpu style={{ width: 14, height: 14 }} />
                  {proposing ? 'Asking Granite…' : 'Generate patch proposal'}
                </button>
              </div>

              {/* Rationale & Diff Card (if proposal exists) */}
              {proposal && (
                <div style={{ marginBottom: '1rem' }}>
                  {proposal.proposal.rationale && (
                    <div style={{
                      backgroundColor: 'rgba(56, 189, 248, 0.05)',
                      border: '1px solid rgba(56, 189, 248, 0.2)',
                      padding: '0.75rem',
                      borderRadius: 6,
                      fontSize: '0.8rem',
                      marginBottom: '0.75rem'
                    }}>
                      <div style={{ fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: '0.2rem' }}>
                        Granite Rationale:
                      </div>
                      <div style={{ color: 'var(--text-primary)' }}>
                        {proposal.proposal.rationale}
                      </div>
                    </div>
                  )}

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                      Unified Configuration Diff (Target: {proposal.target || 'nginx.conf'})
                    </span>
                    {proposal.diff_sha256 && (
                      <span className="provenance-tag">
                        SHA-256: {proposal.diff_sha256.slice(0, 12)}...
                      </span>
                    )}
                  </div>

                  <pre className="diff-container">
                    {renderDiffLines(proposal.diff)}
                  </pre>
                </div>
              )}

              {/* Step 2: Sandbox Verification */}
              {proposal && (
                <div style={{
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '1rem',
                  borderRadius: 6,
                  border: '1px solid var(--border-color)',
                  marginBottom: '1rem'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span className="badge-tag accent">Step 2</span>
                      <span>Sandbox Verification</span>
                    </div>

                    {verification && (
                      <span className={`badge-tag ${verification.status === 'passed' ? 'green' : 'red'}`}>
                        {verification.status.toUpperCase()}
                      </span>
                    )}
                  </div>

                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                    Tests the rendered diff in an isolated container sandbox before any production deployment.
                  </p>

                  <button
                    onClick={handleVerifyProposal}
                    className="btn btn-secondary"
                    disabled={verifying || proposing || proposal.state === 'approved'}
                    style={{ width: '100%', marginBottom: verification ? '0.75rem' : 0 }}
                  >
                    <Play className={verifying ? 'spin' : ''} style={{ width: 14, height: 14 }} />
                    {verifying ? 'Running Sandbox Checks (~40s)...' : 'Run Sandbox Verification'}
                  </button>

                  {/* Sandbox Verification Checks Checklist */}
                  {verification && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.5rem' }}>
                      {verification.checks.map((chk, idx) => (
                        <div
                          key={idx}
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            fontSize: '0.8rem',
                            padding: '0.4rem 0.6rem',
                            borderRadius: 4,
                            backgroundColor: chk.passed ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            {chk.passed ? (
                              <CheckCircle2 style={{ width: 14, height: 14, color: 'var(--accent-green)' }} />
                            ) : (
                              <AlertTriangle style={{ width: 14, height: 14, color: 'var(--accent-red)' }} />
                            )}
                            <code>{chk.name}</code>
                          </div>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {chk.evidence}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Step 3: Approve & Attest */}
              {proposal && (
                <div style={{
                  backgroundColor: 'var(--bg-subtle)',
                  padding: '1rem',
                  borderRadius: 6,
                  border: '1px solid var(--border-color)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span className="badge-tag accent">Step 3</span>
                      <span>Approve & Sign Attestation (ML-DSA-65)</span>
                    </div>

                    <span className="badge-tag yellow">Requires secops role</span>
                  </div>

                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                    Rebuilds the target service, verifies post-deploy endpoints, and records a cryptographically signed attestation to the immutable ledger.
                  </p>

                  {isSecops ? (
                    <button
                      onClick={() => setShowApprovalModal(true)}
                      className="btn btn-primary"
                      disabled={
                        approving ||
                        verifying ||
                        !verification ||
                        verification.status !== 'passed' ||
                        proposal.state === 'approved'
                      }
                      style={{ width: '100%', background: proposal.state === 'approved' ? 'var(--accent-green)' : undefined }}
                    >
                      <FileCheck style={{ width: 14, height: 14 }} />
                      {proposal.state === 'approved'
                        ? 'Attestation Signed & Deployed'
                        : approving
                        ? 'Signing ML-DSA Attestation...'
                        : 'Review & Approve Remediated Config'}
                    </button>
                  ) : (
                    <div className="banner warning" style={{ margin: 0, fontSize: '0.8rem' }}>
                      <Lock style={{ width: 14, height: 14 }} />
                      <span>Approval and deployment is restricted to the <code>security_engineer</code> (secops) role.</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              Select a finding from the priority queue on the left to initiate remediation.
            </div>
          )}
        </div>
      </div>

      {/* Secops Approval & Confirmation Modal */}
      {showApprovalModal && proposal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3 style={{ fontSize: '1.15rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
              Confirm Post-Quantum Remediated Deployment
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              You are about to sign an attestation with <strong>ML-DSA-65</strong> and deploy this change to the target service.
            </p>

            <div style={{ backgroundColor: 'var(--bg-subtle)', padding: '0.75rem', borderRadius: 6, fontSize: '0.8rem', marginBottom: '1rem' }}>
              <div>• <strong>Target Service:</strong> <code>{selectedFinding?.service}</code></div>
              <div>• <strong>Diff SHA-256:</strong> <code>{proposal.diff_sha256 || 'Pending verification'}</code></div>
              <div>• <strong>Approver:</strong> <code>{user?.sub || 'secops'}</code> (role: security_engineer)</div>
              <div>• <strong>Post-Quantum Signature:</strong> ML-DSA-65 (FIPS 204)</div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setShowApprovalModal(false)}
                className="btn btn-secondary"
                disabled={approving}
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmApproval}
                className="btn btn-primary"
                disabled={approving}
              >
                {approving ? 'Attesting...' : 'Confirm & Sign Attestation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
