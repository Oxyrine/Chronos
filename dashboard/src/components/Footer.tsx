import React, { useEffect, useState } from 'react';
import { getLastNegotiatedCurve } from '../api';
import type { SystemHealth } from '../types/contracts';
import { Lock, Activity } from 'lucide-react';

interface FooterProps {
  health: SystemHealth | null;
}

export const Footer: React.FC<FooterProps> = ({ health }) => {
  const [curve, setCurve] = useState<string | null>(getLastNegotiatedCurve());

  useEffect(() => {
    // Check periodically or whenever state updates
    const interval = setInterval(() => {
      const current = getLastNegotiatedCurve();
      if (current !== curve) {
        setCurve(current);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [curve]);

  const displayCurve = curve || (health?.tls_groups && health.tls_groups[0]) || 'X25519MLKEM768 (hybrid)';
  const isHybrid = displayCurve.toLowerCase().includes('mlkem') || displayCurve.toLowerCase().includes('kyber');

  return (
    <footer className="app-footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Activity style={{ width: 14, height: 14, color: health?.status === 'ok' ? 'var(--accent-green)' : 'var(--accent-yellow)' }} />
          <span>Status: <strong>{health?.status === 'ok' ? 'Healthy' : 'Connecting...'}</strong> ({health?.arch || 's390x'})</span>
        </div>
        <span>•</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Lock style={{ width: 14, height: 14, color: isHybrid ? 'var(--accent-green)' : 'var(--accent-yellow)' }} />
          <span>
            Connection TLS Group: <code style={{ color: isHybrid ? 'var(--accent-green)' : 'var(--accent-cyan)' }}>{displayCurve}</code>
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <span style={{ color: 'var(--text-secondary)' }}>
          Discover → Prioritize → Fix → Sign
        </span>
        <span>•</span>
        <span>IBM Z Datathon 2026</span>
      </div>
    </footer>
  );
};
