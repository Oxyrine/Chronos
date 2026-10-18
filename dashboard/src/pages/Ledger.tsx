import React, { useEffect, useState } from 'react';
import { api } from '../api';
import type { Attestation, LedgerChainVerification } from '../types/contracts';
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Key,
  Copy,
  Check,
  Lock
} from 'lucide-react';

export const Ledger: React.FC = () => {
  const [attestations, setAttestations] = useState<Attestation[]>([]);
  const [verification, setVerification] = useState<LedgerChainVerification | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [copiedSeq, setCopiedSeq] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadLedger = async () => {
    try {
      setLoading(true);
      setError(null);
      const [entries, verifyRes] = await Promise.all([
        api.getLedger().catch(() => []),
        api.verifyLedger().catch(() => null),
      ]);
      setAttestations(entries);
      setVerification(verifyRes);
    } catch (err: any) {
      setError(err?.detail || 'Failed to load ML-DSA attestation ledger.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLedger();
  }, []);

  const handleVerifyChain = async () => {
    try {
      setVerifying(true);
      setError(null);
      const res = await api.verifyLedger();
      setVerification(res);
    } catch (err: any) {
      setError(err?.detail || 'Failed to verify ledger integrity chain.');
    } finally {
      setVerifying(false);
    }
  };

  const handleDownloadPublicKey = async () => {
    try {
      const { public_key } = await api.getPublicKey();
      const blob = new Blob([public_key], { type: 'application/x-pem-file' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'mldsa65_public_key.pem';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err?.detail || 'Failed to download public key PEM.');
    }
  };

  const handleCopySig = (seq: number, sig: string) => {
    navigator.clipboard.writeText(sig);
    setCopiedSeq(seq);
    setTimeout(() => setCopiedSeq(null), 2000);
  };

  const downloadEvidence = (seq: number, type: 'cbom' | 'verification' | 'proposal') => {
    window.open(`/api/ledger/${seq}/evidence/${type}`, '_blank');
  };

  return (
    <div className="ledger-page">
      <div className="card">
        <div className="card-header" style={{ flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div className="card-title">
              <ShieldCheck style={{ width: 20, height: 20, color: 'var(--accent-green)' }} />
              <span>Immutable Attestation Ledger (ML-DSA-65)</span>
            </div>
            <div className="card-subtitle">
              Cryptographically signed attestation log of all approved configuration remediations with SHA-256 Merkle links.
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <button
              onClick={handleVerifyChain}
              className="btn btn-secondary"
              disabled={verifying}
            >
              <CheckCircle2 style={{ width: 14, height: 14, color: 'var(--accent-green)' }} />
              {verifying ? 'Verifying Chain...' : 'Verify Hash Chain'}
            </button>
            <button
              onClick={handleDownloadPublicKey}
              className="btn btn-secondary"
            >
              <Key style={{ width: 14, height: 14 }} />
              Download Signer Public Key (PEM)
            </button>
          </div>
        </div>

        {/* Chain Integrity Banner */}
        {verification && (
          <div
            className={`banner ${verification.chain_ok ? 'info' : 'error'}`}
            style={{
              marginBottom: '1rem',
              backgroundColor: verification.chain_ok ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
              borderColor: verification.chain_ok ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
              color: verification.chain_ok ? 'var(--accent-green)' : 'var(--accent-red)'
            }}
          >
            {verification.chain_ok ? (
              <CheckCircle2 style={{ width: 18, height: 18, flexShrink: 0 }} />
            ) : (
              <AlertTriangle style={{ width: 18, height: 18, flexShrink: 0 }} />
            )}
            <div>
              <strong>
                {verification.chain_ok
                  ? 'Ledger Chain Intact & Verified'
                  : `Tampering Detected at Sequence #${verification.bad_seq}`}
              </strong>
              <div style={{ fontSize: '0.75rem', marginTop: '0.2rem', color: 'var(--text-secondary)' }}>
                {verification.chain_ok
                  ? `Every entry is chained via SHA-256 and verified against the ML-DSA-65 signing key (${verification.mode || 'live'}).`
                  : 'Hash mismatch or invalid signature detected. Investigation required.'}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="banner error" style={{ marginBottom: '1rem' }}>
            <AlertTriangle style={{ width: 14, height: 14 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Attestation Table */}
        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Seq & Time</th>
                <th>Proposal ID</th>
                <th>Approved By</th>
                <th>Algorithm</th>
                <th>Cryptographic Hashes</th>
                <th>Signature (sig_b64)</th>
                <th>Evidence Artifacts</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem' }}>
                    Loading attestation ledger...
                  </td>
                </tr>
              ) : attestations.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                    No attestations recorded yet. Remediations approved in the Remediation Queue will appear here.
                  </td>
                </tr>
              ) : (
                attestations.map((entry) => (
                  <tr key={entry.seq}>
                    <td>
                      <div>
                        <strong style={{ color: 'var(--accent-cyan)' }}>#{entry.seq}</strong>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {new Date(entry.ts).toLocaleTimeString()}
                      </div>
                    </td>
                    <td>
                      <code>{entry.proposal_id}</code>
                    </td>
                    <td>
                      <span className="badge-tag accent">
                        {entry.approved_by}
                      </span>
                    </td>
                    <td>
                      <span className="badge-tag green">
                        <Lock style={{ width: 10, height: 10, display: 'inline', marginRight: 4 }} />
                        {entry.alg}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontSize: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>prev:</span>{' '}
                          <code>{entry.prev_hash ? entry.prev_hash.slice(0, 10) : 'genesis'}...</code>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>verify:</span>{' '}
                          <code>{entry.verification_sha256 ? entry.verification_sha256.slice(0, 10) : 'n/a'}...</code>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-muted)' }}>cbom:</span>{' '}
                          <code>{entry.cbom_sha256 ? entry.cbom_sha256.slice(0, 10) : 'n/a'}...</code>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <code style={{ fontSize: '0.75rem', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {entry.sig_b64.slice(0, 16)}...
                        </code>
                        <button
                          onClick={() => handleCopySig(entry.seq, entry.sig_b64)}
                          className="btn btn-secondary"
                          style={{ padding: '0.2rem 0.4rem', fontSize: '0.7rem' }}
                          title="Copy full base64 signature"
                        >
                          {copiedSeq === entry.seq ? (
                            <Check style={{ width: 12, height: 12, color: 'var(--accent-green)' }} />
                          ) : (
                            <Copy style={{ width: 12, height: 12 }} />
                          )}
                        </button>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.35rem' }}>
                        <button
                          onClick={() => downloadEvidence(entry.seq, 'proposal')}
                          className="btn btn-secondary"
                          style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                          title="Download Diff Proposal"
                        >
                          diff
                        </button>
                        <button
                          onClick={() => downloadEvidence(entry.seq, 'verification')}
                          className="btn btn-secondary"
                          style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                          title="Download Sandbox Verification Log"
                        >
                          log
                        </button>
                        <button
                          onClick={() => downloadEvidence(entry.seq, 'cbom')}
                          className="btn btn-secondary"
                          style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                          title="Download CBOM Snapshot"
                        >
                          cbom
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Compliance Disclaimer */}
      <div style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '1rem' }}>
        Attestations are cryptographically signed with NIST FIPS 204 ML-DSA-65 and chained using SHA-256. Verified on IBM Z LinuxONE (s390x).
      </div>
    </div>
  );
};
