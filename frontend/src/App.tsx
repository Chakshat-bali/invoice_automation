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
        padding: '20px 40px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'rgba(255, 255, 255, 0.6)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-light)',
        position: 'sticky',
        top: 0,
        zIndex: 100
      }}>
        <Link to="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Home size={22} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
            <span style={{ fontSize: '20px', fontWeight: 800, color: 'var(--text-title)', lineHeight: '1.2' }}>AI Invoice Automation</span>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', marginTop: '2px' }}>Python FastAPI &nbsp;·&nbsp; OCR &nbsp;·&nbsp; Multimodal AI</span>
          </div>
        </Link>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
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
