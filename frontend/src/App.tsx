import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { Home, LayoutDashboard } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import InvoiceDashboard from './pages/InvoiceDashboard';
import Review from './pages/Review';
import { API_URL } from './api';

function App() {
  useEffect(() => {
    const handleUnload = () => {
      const sid = sessionStorage.getItem('invoice_session_id');
      if (sid && sid !== 'default') {
        navigator.sendBeacon(`${API_URL}/session/${sid}/end`);
      }
    };
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
  }, []);

  return (
    <BrowserRouter>
      <header style={{
        padding: '16px 40px',
        display: 'grid',
        gridTemplateColumns: '1fr auto 1fr',
        alignItems: 'center',
        background: 'rgba(255, 255, 255, 0.9)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-light)',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        <div style={{ justifySelf: 'start' }}>
          <Link to="/" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', textDecoration: 'none', display: 'flex', alignItems: 'center' }}>
            <Home size={22} style={{ color: 'var(--accent)' }} />
          </Link>
        </div>
        <div style={{ justifySelf: 'center', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <h1 style={{
            fontSize: '42px',
            fontWeight: 800,
            background: 'linear-gradient(135deg, var(--text-title), var(--accent))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            margin: 0,
            letterSpacing: '-0.02em',
            lineHeight: '1.1'
          }}>
            AI Invoice Automation
          </h1>
          <p style={{
            fontSize: '16px',
            color: 'var(--accent)',
            fontWeight: 800,
            margin: '8px 0 0',
            letterSpacing: '0.02em'
          }}>
            Python FastAPI &nbsp;·&nbsp; OCR &nbsp;·&nbsp; Multimodal AI
          </p>
        </div>
        <div style={{ justifySelf: 'end', display: 'flex', gap: '24px', alignItems: 'center' }}>
          <Link
            to="/invoices"
            title="Invoice Dashboard"
            style={{
              textDecoration: 'none',
              color: 'var(--accent)',
              fontWeight: 600,
              fontSize: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              background: 'var(--accent-light)',
              padding: '6px 12px',
              borderRadius: '8px',
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => (e.currentTarget.style.background = 'rgba(79, 70, 229, 0.15)')}
            onMouseOut={(e) => (e.currentTarget.style.background = 'var(--accent-light)')}
          >
            <LayoutDashboard size={16} />
            <span>Dashboard</span>
          </Link>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/invoices" element={<InvoiceDashboard />} />
        <Route path="/review/:id" element={<Review />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
