import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './api';
import type { UserSession, SystemHealth } from './types/contracts';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';
import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Inventory } from './pages/Inventory';
import { Shelflife } from './pages/Shelflife';
import { Remediation } from './pages/Remediation';
import { Ledger } from './pages/Ledger';

export function App() {
  const [user, setUser] = useState<UserSession | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const checkAuth = async () => {
    try {
      const session = await api.me();
      setUser(session);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const fetchHealth = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
    } catch {
      // API might be spinning up
    }
  };

  useEffect(() => {
    checkAuth();
    fetchHealth();

    const handleUnauthorized = () => {
      setUser(null);
    };

    window.addEventListener('chronos:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('chronos:unauthorized', handleUnauthorized);
    };
  }, []);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignore logout network errors
    } finally {
      setUser(null);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: 'var(--bg-dark)' }}>
        <div style={{ textAlign: 'center', color: 'var(--accent-cyan)' }}>
          <div style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.5rem' }}>Loading Chronos...</div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Connecting to LinuxONE API</div>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Navbar user={user} health={health} onLogout={handleLogout} />

        <main className="main-content">
          <Routes>
            <Route path="/login" element={<Login onLoginSuccess={(u) => setUser(u)} />} />
            <Route path="/overview" element={<Overview />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/shelflife" element={<Shelflife user={user} />} />
            <Route path="/remediation" element={<Remediation user={user} />} />
            <Route path="/ledger" element={<Ledger />} />
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>

        <Footer health={health} />
      </div>
    </BrowserRouter>
  );
}

export default App;
