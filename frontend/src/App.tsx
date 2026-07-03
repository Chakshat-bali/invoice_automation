import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { fetchSheetsLink } from './api';
import { Layers, FileSpreadsheet, ExternalLink } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Review from './pages/Review';

function App() {
  const [sheetUrl, setSheetUrl] = useState<string | null>(null);

  useEffect(() => {
    fetchSheetsLink()
      .then(res => setSheetUrl(res.url))
      .catch(err => console.error("Error getting sheet link", err));
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
        <Link to="/" style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Layers size={22} style={{ color: 'var(--accent)' }} />
          <span>Nexus</span>
        </Link>
        <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
          <Link to="/" style={{ textDecoration: 'none', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '14px', transition: 'color 0.2s' }}>
            Dashboard
          </Link>
          {sheetUrl && (
            <a 
              href={sheetUrl} 
              target="_blank" 
              rel="noreferrer" 
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
              onMouseOver={(e) => e.currentTarget.style.background = 'rgba(79, 70, 229, 0.15)'}
              onMouseOut={(e) => e.currentTarget.style.background = 'var(--accent-light)'}
            >
              <FileSpreadsheet size={16} />
              <span>Live Google Sheet</span>
              <ExternalLink size={12} />
            </a>
          )}
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/review/:id" element={<Review />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
