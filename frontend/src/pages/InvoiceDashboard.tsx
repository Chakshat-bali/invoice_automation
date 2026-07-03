import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { type Invoice, fetchInvoices, deleteInvoice, pollEmailInbox, fetchGoogleAuthStatus, fetchSheetsLink, type GoogleAuthStatus } from '../api';
import {
    FileSpreadsheet,
    Trash2,
    Edit3,
    Search,
    Loader2,
    MailCheck,
    LayoutDashboard,
    ChevronDown,
    ExternalLink,
} from 'lucide-react';
import { API_URL } from '../api';
import './Dashboard.css';

export default function InvoiceDashboard() {
    const navigate = useNavigate();
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [statusFilter, setStatusFilter] = useState('');
    const [vendorFilter, setVendorFilter] = useState('');
    const [isPollingEmail, setIsPollingEmail] = useState(false);
    const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatus>({ connected: false, email: null });
    const [showExportDropdown, setShowExportDropdown] = useState(false);
    const [sheetsUrl, setSheetsUrl] = useState<string | null>(null);
    const exportDropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadInvoices();
        loadGoogleStatus();
        fetchSheetsLink()
            .then(res => setSheetsUrl(res.url))
            .catch(err => console.error('Error getting sheet link', err));
    }, [statusFilter, vendorFilter]);

    // Close dropdown on outside click
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (exportDropdownRef.current && !exportDropdownRef.current.contains(e.target as Node)) {
                setShowExportDropdown(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    async function loadGoogleStatus() {
        try {
            const status = await fetchGoogleAuthStatus();
            setGoogleStatus(status);
        } catch (e) {
            console.error('Error loading google status', e);
        }
    }

    async function loadInvoices() {
        try {
            const data = await fetchInvoices(statusFilter, vendorFilter);
            setInvoices(data);
        } catch (error) {
            console.error('Failed to load invoices:', error);
        }
    }

    async function handlePollEmail() {
        if (!googleStatus.connected) {
            alert('Please connect your Google Gmail account first before syncing email invoices!');
            return;
        }
        setIsPollingEmail(true);
        try {
            const res = await pollEmailInbox();
            alert(`Gmail sync complete! Processed ${res.processed} new invoices.`);
            await loadInvoices();
        } catch (error) {
            alert('Gmail sync failed: ' + (error as Error).message);
        } finally {
            setIsPollingEmail(false);
        }
    }

    const total = invoices.length;
    const pending = invoices.filter(i => i.status === 'pending_review').length;
    const approved = invoices.filter(i => i.status === 'approved').length;
    const rejected = invoices.filter(i => i.status === 'rejected').length;

    return (
        <div style={{ minHeight: '100vh' }}>
            {/* Page Header */}
            <div style={{
                maxWidth: '1200px',
                margin: '0 auto',
                padding: '48px 20px 24px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '16px'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                    <div style={{
                        background: 'var(--accent-light)',
                        padding: '10px',
                        borderRadius: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                    }}>
                        <LayoutDashboard size={22} style={{ color: 'var(--accent)' }} />
                    </div>
                    <div>
                        <h1 style={{
                            fontSize: '26px',
                            fontWeight: 800,
                            background: 'linear-gradient(135deg, var(--text-title), var(--accent))',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            letterSpacing: '-0.02em',
                            margin: 0
                        }}>
                            Invoice Dashboard
                        </h1>
                        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: '2px 0 0' }}>
                            Manage, review and export all processed invoices
                        </p>
                    </div>
                </div>
                <button
                    onClick={() => navigate('/')}
                    className="btn-outline"
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 18px', fontSize: '14px' }}
                >
                    ← Back to Home
                </button>
            </div>

            {/* Summary Stats */}
            <div style={{
                maxWidth: '1200px',
                margin: '0 auto 28px',
                padding: '0 20px',
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '16px'
            }}>
                {[
                    { label: 'Total Processed', value: total, cls: 'total' },
                    { label: 'Pending Review',  value: pending,  cls: 'pending' },
                    { label: 'Approved',         value: approved, cls: 'approved' },
                    { label: 'Rejected',         value: rejected, cls: 'rejected' },
                ].map(({ label, value, cls }) => (
                    <div key={label} className={`glass-card`} style={{ padding: '20px 24px' }}>
                        <div className={`stat-value ${cls}`} style={{ fontSize: '32px', fontWeight: 800 }}>{value}</div>
                        <div className="stat-label" style={{ fontSize: '12px', marginTop: '4px' }}>{label}</div>
                    </div>
                ))}
            </div>

            {/* Table Section */}
            <div className="list-section" style={{ paddingTop: 0 }}>
                <div className="table-container">
                    <div className="table-header-controls">
                        <h2>Recent Invoices</h2>
                        <div className="controls-group">
                            <button
                                onClick={handlePollEmail}
                                disabled={isPollingEmail}
                                className="btn-outline"
                                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px' }}
                            >
                                {isPollingEmail
                                    ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
                                    : <MailCheck size={18} />}
                                Sync Email
                            </button>
                            <div style={{ position: 'relative' }} ref={exportDropdownRef}>
                                <button
                                    onClick={() => setShowExportDropdown(!showExportDropdown)}
                                    className="btn-primary"
                                    style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px' }}
                                >
                                    <FileSpreadsheet size={18} />
                                    Export to Excel
                                    <ChevronDown size={14} style={{ marginLeft: '2px', transform: showExportDropdown ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }} />
                                </button>
                                {showExportDropdown && (
                                    <div style={{
                                        position: 'absolute',
                                        top: 'calc(100% + 8px)',
                                        right: 0,
                                        background: 'white',
                                        border: '1px solid var(--border-light)',
                                        borderRadius: '8px',
                                        boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                                        minWidth: '210px',
                                        zIndex: 100,
                                        overflow: 'hidden'
                                    }}>
                                        {sheetsUrl && (
                                            <a
                                                href={sheetsUrl}
                                                target="_blank"
                                                rel="noreferrer"
                                                style={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '10px',
                                                    padding: '12px 16px',
                                                    textDecoration: 'none',
                                                    color: 'var(--text-primary)',
                                                    borderBottom: '1px solid var(--border-light)',
                                                    transition: 'background 0.2s'
                                                }}
                                                onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                                                onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                                                onClick={() => setShowExportDropdown(false)}
                                            >
                                                <FileSpreadsheet size={16} style={{ color: 'var(--accent)' }} />
                                                <span style={{ fontSize: '14px', fontWeight: 500 }}>View in Google Sheets</span>
                                                <ExternalLink size={12} style={{ marginLeft: 'auto', opacity: 0.6 }} />
                                            </a>
                                        )}
                                        <button
                                            onClick={() => {
                                                window.open(`${API_URL}/export/excel`, '_blank');
                                                setShowExportDropdown(false);
                                            }}
                                            style={{
                                                all: 'unset',
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '10px',
                                                padding: '12px 16px',
                                                width: '100%',
                                                boxSizing: 'border-box',
                                                cursor: 'pointer',
                                                transition: 'background 0.2s'
                                            }}
                                            onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                                            onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                                        >
                                            <FileSpreadsheet size={16} style={{ color: 'var(--success)' }} />
                                            <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--text-primary)' }}>Export to Excel</span>
                                        </button>
                                    </div>
                                )}
                            </div>
                            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                <Search size={16} style={{ position: 'absolute', left: '12px', color: 'var(--text-secondary)', pointerEvents: 'none' }} />
                                <input
                                    type="text"
                                    className="text-input"
                                    placeholder="Search vendor..."
                                    value={vendorFilter}
                                    onChange={(e) => setVendorFilter(e.target.value)}
                                    style={{ paddingLeft: '36px' }}
                                />
                            </div>
                        </div>
                    </div>

                    <div style={{ overflowX: 'auto', borderRadius: '12px', border: '1px solid var(--border-light)' }}>
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>File Name</th>
                                    <th>Date Added</th>
                                    <th>Vendor</th>
                                    <th>Amount</th>
                                    <th>
                                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                            <select
                                                value={statusFilter}
                                                onChange={(e) => setStatusFilter(e.target.value)}
                                                style={{
                                                    background: 'none',
                                                    border: 'none',
                                                    fontWeight: 'bold',
                                                    color: 'var(--text-secondary)',
                                                    cursor: 'pointer',
                                                    fontSize: '12px',
                                                    padding: 0,
                                                    outline: 'none',
                                                    textTransform: 'uppercase',
                                                    letterSpacing: '0.5px',
                                                    fontFamily: 'inherit'
                                                }}
                                            >
                                                <option value="">Status</option>
                                                <option value="pending_review">Pending</option>
                                                <option value="approved">Approved</option>
                                                <option value="rejected">Rejected</option>
                                            </select>
                                        </div>
                                    </th>
                                    <th style={{ textAlign: 'right' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {invoices.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>
                                            No invoices found. Upload one from the home page!
                                        </td>
                                    </tr>
                                ) : (
                                    invoices.map(inv => (
                                        <tr
                                            key={inv.invoice_id}
                                            style={{ cursor: 'pointer' }}
                                            onClick={() => navigate(`/review/${inv.invoice_id}`)}
                                        >
                                            <td style={{ fontWeight: 500 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                    <span>{inv.original_filename}</span>
                                                    {inv.is_duplicate && (
                                                        <span
                                                            className="badge rejected"
                                                            style={{ fontSize: '10px', padding: '2px 6px', textTransform: 'uppercase' }}
                                                            title="Duplicate of another invoice"
                                                        >
                                                            Duplicate
                                                        </span>
                                                    )}
                                                </div>
                                            </td>
                                            <td style={{ color: 'var(--text-secondary)' }}>
                                                {new Date(inv.created_at).toLocaleDateString()}
                                            </td>
                                            <td>{inv.vendor_name || '-'}</td>
                                            <td style={{ fontWeight: 600 }}>
                                                {inv.total_amount ? `$${inv.total_amount.toFixed(2)}` : '-'}
                                            </td>
                                            <td>
                                                <span className={`badge ${inv.status}`}>
                                                    {inv.status.replace('_', ' ')}
                                                </span>
                                            </td>
                                            <td style={{ textAlign: 'right' }}>
                                                <button
                                                    className="action-btn"
                                                    title="Edit/Review"
                                                    onClick={(e) => { e.stopPropagation(); navigate(`/review/${inv.invoice_id}`); }}
                                                >
                                                    <Edit3 size={16} />
                                                </button>
                                                <button
                                                    className="action-btn"
                                                    title="Delete"
                                                    style={{ color: 'var(--danger)' }}
                                                    onClick={async (e) => {
                                                        e.stopPropagation();
                                                        if (window.confirm('Delete this invoice?')) {
                                                            await deleteInvoice(inv.invoice_id);
                                                            loadInvoices();
                                                        }
                                                    }}
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
}
