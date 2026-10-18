import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api';
import { Shield, KeyRound, AlertTriangle, Info } from 'lucide-react';
import type { UserSession } from '../types/contracts';

interface LoginProps {
  onLoginSuccess: (user: UserSession) => void;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Please provide both username and password.');
      return;
    }

    setError(null);
    setSubmitting(true);

    try {
      const user = await api.login(username.trim(), password);
      onLoginSuccess(user);
      navigate('/overview');
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setError('Rate limit exceeded (5 failed attempts per 15 min). Please try again later.');
        } else {
          setError(err.detail || 'Invalid username or password.');
        }
      } else {
        setError('Connection failed. Please verify API availability.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '80vh', padding: '1rem' }}>
      <div className="card" style={{ maxWidth: 440, width: '100%', padding: '2rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div style={{ display: 'inline-flex', padding: '0.75rem', borderRadius: '50%', backgroundColor: 'rgba(56, 189, 248, 0.1)', marginBottom: '0.75rem' }}>
            <Shield style={{ width: 36, height: 36, color: 'var(--accent-cyan)' }} />
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, letterSpacing: '-0.025em' }}>Chronos Console</h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
            Post-Quantum Risk Profiling & Remediation
          </p>
        </div>

        {error && (
          <div className="banner error" style={{ marginBottom: '1rem' }}>
            <AlertTriangle style={{ width: 16, height: 16, flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
              Username
            </label>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. secops or viewer"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
              autoFocus
              required
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '0.4rem' }}>
              Password
            </label>
            <input
              type="password"
              className="input-field"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', padding: '0.75rem' }}
            disabled={submitting}
          >
            <KeyRound style={{ width: 16, height: 16 }} />
            {submitting ? 'Authenticating...' : 'Sign In'}
          </button>
        </form>

        <div className="banner info" style={{ marginTop: '1.5rem', fontSize: '0.8rem', flexDirection: 'column', alignItems: 'flex-start', gap: '0.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}>
            <Info style={{ width: 14, height: 14 }} /> Role Permissions:
          </div>
          <div>• <strong>secops</strong> (<code>security_engineer</code>): Full remediation, sandbox verification & attestation signing.</div>
          <div>• <strong>viewer</strong> (<code>viewer</code>): Read-only audit of CBOM, exposure models & ledger.</div>
        </div>
      </div>
    </div>
  );
};
