import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Shield, Cpu, User, LogOut } from 'lucide-react';
import type { UserSession, SystemHealth } from '../types/contracts';

interface NavbarProps {
  user: UserSession | null;
  health: SystemHealth | null;
  onLogout: () => Promise<void>;
}

export const Navbar: React.FC<NavbarProps> = ({ user, health, onLogout }) => {
  const navigate = useNavigate();

  const handleLogout = async () => {
    await onLogout();
    navigate('/login');
  };

  const isSecops = user?.role === 'security_engineer';

  return (
    <header className="app-header">
      <div className="brand-section">
        <NavLink to="/overview" className="brand-logo">
          <Shield className="w-5 h-5 text-accent-cyan" style={{ color: 'var(--accent-cyan)' }} />
          <span>CHRONOS</span>
        </NavLink>
        <span className="badge-tag accent">
          {health?.arch ? `${health.arch}` : 's390x'}
        </span>
        <span className="badge-tag" title="Disclosed: CPU-only inference, NNPA not configured">
          <Cpu style={{ width: 12, height: 12, display: 'inline', marginRight: 4 }} />
          NNPA: {health?.nnpa ? 'yes' : 'no'}
        </span>
      </div>

      <nav className="nav-links" aria-label="Main Navigation">
        <NavLink to="/overview" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          Overview
        </NavLink>
        <NavLink to="/inventory" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          Inventory (CBOM)
        </NavLink>
        <NavLink to="/shelflife" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          Shelf-Life Profiling
        </NavLink>
        <NavLink to="/remediation" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          Remediation Queue
        </NavLink>
        <NavLink to="/ledger" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          ML-DSA Ledger
        </NavLink>
      </nav>

      <div className="user-section">
        {user ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <User style={{ width: 16, height: 16, color: 'var(--text-secondary)' }} />
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{user.sub}</span>
              <span className={`badge-tag ${isSecops ? 'accent' : 'yellow'}`}>
                {isSecops ? 'secops' : 'viewer'}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="btn btn-secondary"
              style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
              title="Log out"
            >
              <LogOut style={{ width: 14, height: 14 }} />
              Logout
            </button>
          </>
        ) : (
          <NavLink to="/login" className="btn btn-primary" style={{ padding: '0.35rem 0.85rem', fontSize: '0.85rem' }}>
            Login
          </NavLink>
        )}
      </div>
    </header>
  );
};
