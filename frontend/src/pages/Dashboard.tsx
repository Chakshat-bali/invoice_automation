import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { type Invoice, fetchInvoices, uploadInvoice, deleteInvoice, pollEmailInbox, fetchGoogleAuthStatus, disconnectGoogleAuth, fetchGoogleAuthUrl, type GoogleAuthStatus } from '../api';
import {
    UploadCloud,
    Activity,
    FileSpreadsheet,
    Trash2,
    Edit3,
    Search,
    ChevronDown,
    BookOpen,
    Loader2,
    MailCheck,
    Link as LinkIcon,
    Link2Off,
    Check
} from 'lucide-react';
import './Dashboard.css';
import { API_URL } from "../api";

export default function Dashboard() {
    const navigate = useNavigate();
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [statusFilter, setStatusFilter] = useState('');
    const [vendorFilter, setVendorFilter] = useState('');
    const [isUploading, setIsUploading] = useState(false);
    const [isPollingEmail, setIsPollingEmail] = useState(false);
    const [isDragOver, setIsDragOver] = useState(false);
    const [processingInvoiceId, setProcessingInvoiceId] = useState<string | null>(null);
    const [processingComplete, setProcessingComplete] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [showGuide, setShowGuide] = useState(true);
    const [googleStatus, setGoogleStatus] = useState<GoogleAuthStatus>({ connected: false, email: null });
    const [showConnectModal, setShowConnectModal] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;
        if (processingInvoiceId && !processingComplete) {
            interval = setInterval(async () => {
                try {
                    const { fetchInvoice } = await import('../api');
                    const inv = await fetchInvoice(processingInvoiceId);
                    if (inv.status === 'error') {
                        setProcessingInvoiceId(null);
                        setProcessingComplete(false);
                        alert(inv.validation_notes || "Please upload a valid invoice file");
                        loadInvoices();
                    } else if (inv.status !== 'processing') {
                        // Mark complete but keep modal open so user can rename
                        setProcessingComplete(true);
                        loadInvoices();
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }, 2000);
        }
        return () => clearInterval(interval);
    }, [processingInvoiceId, processingComplete]);

    useEffect(() => {
        loadInvoices();
    }, [statusFilter, vendorFilter]);

    useEffect(() => {
        loadGoogleStatus();
    }, []);

    async function loadGoogleStatus() {
        try {
            const status = await fetchGoogleAuthStatus();
            setGoogleStatus(status);
        } catch (e) {
            console.error("Error loading google status", e);
        }
    }

    async function handleConnectGoogle() {
        try {
            const { url } = await fetchGoogleAuthUrl();
            window.location.href = url;
        } catch (e) {
            alert("Failed to initiate Google OAuth: " + (e as Error).message);
        }
    }

    async function handleDisconnectGoogle() {
        if (window.confirm("Are you sure you want to disconnect your Google account?")) {
            try {
                await disconnectGoogleAuth();
                await loadGoogleStatus();
                alert("Disconnected successfully!");
            } catch (e) {
                alert("Failed to disconnect: " + (e as Error).message);
            }
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

    async function handleFileSelect(file: File) {
        setIsUploading(true);
        try {
            const result = await uploadInvoice(file);
            setRenameValue(result.original_filename);
            setProcessingInvoiceId(result.invoice_id);
            await loadInvoices();
        } catch (error) {
            alert('Upload failed: ' + (error as Error).message);
        } finally {
            setIsUploading(false);
        }
    }

    async function handleRenameSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!processingInvoiceId) return;
        try {
            const { updateInvoice } = await import('../api');
            await updateInvoice(processingInvoiceId, { original_filename: renameValue });
            await loadInvoices();
            setProcessingInvoiceId(null);
            setProcessingComplete(false);
        } catch (error) {
            console.error("Failed to rename", error);
        }
    }

    function handleGoToReview() {
        const id = processingInvoiceId;
        setProcessingInvoiceId(null);
        setProcessingComplete(false);
        if (id) navigate(`/review/${id}`);
    }

    async function handleCancelProcessing() {
        if (!processingInvoiceId) return;
        const toCancel = processingInvoiceId;
        setProcessingInvoiceId(null);
        setProcessingComplete(false);
        try {
            await deleteInvoice(toCancel);
            await loadInvoices();
            alert("Processing cancelled.");
        } catch (error) {
            console.error("Failed to cancel processing", error);
        }
    }

    async function handlePollEmail() {
        if (!googleStatus.connected) {
            alert("Please connect your Google Gmail account first before syncing email invoices!");
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
        <div>
            <div className="hero">
                <h1>AI Invoice Automation</h1>
                <p className="hero-stack">Python FastAPI &nbsp;·&nbsp; OCR &nbsp;·&nbsp; Multimodal AI</p>
                <p>Upload your invoices to our AI extraction engine to automatically digitize vendor details, line items, and totals in real-time. Review the results below.</p>
            </div>

            {/* Interactive User Guide */}
            <div className="guide-container">
                <div className="guide-card">
                    <div className="guide-header" onClick={() => setShowGuide(!showGuide)}>
                        <div className="guide-title">
                            <BookOpen className="guide-icon-blue" size={20} />
                            <span>Quick Onboarding Guide & Instructions</span>
                        </div>
                        <ChevronDown className={`guide-toggle ${showGuide ? 'open' : ''}`} size={20} />
                    </div>
                    {showGuide && (
                        <>
                            <div className="guide-content">
                                <div className="guide-step">
                                    <div className="step-num">1</div>
                                    <h3>Upload Invoice</h3>
                                    <p>Drag and drop your invoice PDF or image into the upload area. The system will start uploading and processing it asynchronously.</p>
                                </div>
                                <div className="guide-step">
                                    <div className="step-num">2</div>
                                    <h3>Rename & Poll</h3>
                                    <p>While the AI parses your invoice in the background, you can rename the file. Once processing completes, you will be redirected to review.</p>
                                </div>
                                <div className="guide-step">
                                    <div className="step-num">3</div>
                                    <h3>Validate & Export</h3>
                                    <p>Double-check the extracted values. The AI will highlight mathematical mismatches (like incorrect tax rates). Click Approve to sync with Google Sheets!</p>
                                </div>
                            </div>

                            {/* Gmail OAuth connection status */}
                            <div style={{
                                marginTop: '24px',
                                paddingTop: '20px',
                                borderTop: '1px solid var(--border-light)',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                flexWrap: 'wrap',
                                gap: '16px'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    <MailCheck className={googleStatus.connected ? "guide-icon-blue" : ""} size={20} style={{ color: googleStatus.connected ? 'var(--success)' : 'var(--text-secondary)' }} />
                                    <span style={{ fontSize: '14px', fontWeight: 600 }}>
                                        {googleStatus.connected ? (
                                            <span style={{ color: 'var(--success)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                                                <Check size={16} /> Connected: {googleStatus.email}
                                            </span>
                                        ) : (
                                            <span style={{ color: 'var(--text-secondary)' }}>Gmail: Not Connected</span>
                                        )}
                                    </span>
                                </div>
                                <div>
                                    {googleStatus.connected ? (
                                        <button
                                            onClick={handleDisconnectGoogle}
                                            className="btn-outline"
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '8px',
                                                padding: '8px 16px',
                                                borderColor: 'var(--danger-light)',
                                                color: 'var(--danger)'
                                            }}
                                            onMouseOver={(e) => e.currentTarget.style.background = 'var(--danger-light)'}
                                            onMouseOut={(e) => e.currentTarget.style.background = 'white'}
                                        >
                                            <Link2Off size={16} /> Disconnect Account
                                        </button>
                                    ) : (
                                        <button
                                            onClick={() => setShowConnectModal(true)}
                                            className="btn-primary"
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '8px',
                                                padding: '8px 16px',
                                                fontSize: '14px'
                                            }}
                                        >
                                            <LinkIcon size={16} /> Connect Gmail Account
                                        </button>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>

            <div className="main-container">
                {/* Upload Card */}
                <div className="glass-card">
                    <div className="card-header">
                        <UploadCloud className="guide-icon-blue" size={20} />
                        <h2>Upload Invoice (PDF/Image)</h2>
                    </div>
                    <div className="card-body">
                        <div
                            className={`upload-area ${isDragOver ? 'dragover' : ''}`}
                            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                            onDragLeave={() => setIsDragOver(false)}
                            onDrop={(e) => {
                                e.preventDefault();
                                setIsDragOver(false);
                                if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]);
                            }}
                            onClick={() => !isUploading && fileInputRef.current?.click()}
                        >
                            <UploadCloud className="upload-icon" size={48} style={{ color: 'var(--accent)', marginBottom: '16px' }} />
                            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>Select a file or drag and drop</h3>
                            <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '24px' }}>PDF, JPG, PNG up to 10MB</p>
                            <button className="btn-primary">Choose File</button>
                            <input
                                type="file"
                                ref={fileInputRef}
                                accept=".pdf,.jpg,.jpeg,.png,.tiff,.bmp"
                                style={{ display: 'none' }}
                                onChange={(e) => {
                                    if (e.target.files && e.target.files.length > 0) {
                                        handleFileSelect(e.target.files[0]);
                                    }
                                }}
                            />
                        </div>
                    </div>
                </div>

                {/* Stats Card */}
                <div className="glass-card">
                    <div className="card-header">
                        <Activity className="guide-icon-blue" size={20} />
                        <h2>System Overview</h2>
                    </div>
                    <div className="card-body">
                        <div className="stat-grid">
                            <div className="stat-item total">
                                <div className="stat-value">{total}</div>
                                <div className="stat-label">Total Processed</div>
                            </div>
                            <div className="stat-item pending">
                                <div className="stat-value">{pending}</div>
                                <div className="stat-label">Pending Review</div>
                            </div>
                            <div className="stat-item approved">
                                <div className="stat-value">{approved}</div>
                                <div className="stat-label">Approved</div>
                            </div>
                            <div className="stat-item rejected">
                                <div className="stat-value">{rejected}</div>
                                <div className="stat-label">Rejected</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* List Section */}
            <div className="list-section">
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
                                {isPollingEmail ? <Loader2 size={18} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} /> : <MailCheck size={18} />}
                                Sync Email
                            </button>
                            <button
                                onClick={() => {
                                    window.open(`${API_URL}/export/excel`, "_blank");
                                }}
                                className="btn-primary"
                                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px' }}
                            >
                                <FileSpreadsheet size={18} /> Export to Excel
                            </button>

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
                                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '60px', color: 'var(--text-secondary)' }}>No invoices found. Start by uploading one above!</td></tr>
                                ) : (
                                    invoices.map(inv => (
                                        <tr key={inv.invoice_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/review/${inv.invoice_id}`)}>
                                            <td style={{ fontWeight: 500 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                    <span>{inv.original_filename}</span>
                                                    {inv.is_duplicate && (
                                                        <span className="badge rejected" style={{ fontSize: '10px', padding: '2px 6px', textTransform: 'uppercase' }} title="Duplicate of another invoice">
                                                            Duplicate
                                                        </span>
                                                    )}
                                                </div>
                                            </td>
                                            <td style={{ color: 'var(--text-secondary)' }}>{new Date(inv.created_at).toLocaleDateString()}</td>
                                            <td>{inv.vendor_name || '-'}</td>
                                            <td style={{ fontWeight: 600 }}>{inv.total_amount ? `$${inv.total_amount.toFixed(2)}` : '-'}</td>
                                            <td>
                                                <span className={`badge ${inv.status}`}>
                                                    {inv.status.replace('_', ' ')}
                                                </span>
                                            </td>
                                            <td style={{ textAlign: 'right' }}>
                                                <button className="action-btn" title="Edit/Review" onClick={(e) => { e.stopPropagation(); navigate(`/review/${inv.invoice_id}`); }}>
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

            {/* Modal Overlay for Uploading & Processing */}
            {(isUploading || processingInvoiceId) && (
                <div className="modal-overlay">
                    <div className="modal-content">
                        {!processingComplete && (
                            <Loader2 className="spinner animate-spin" size={40} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite', marginBottom: '20px' }} />
                        )}
                        {processingComplete && (
                            <div style={{ fontSize: '40px', marginBottom: '16px' }}>✅</div>
                        )}
                        {isUploading ? (
                            <h3 style={{ fontWeight: 600, color: 'var(--text-title)' }}>Uploading invoice...</h3>
                        ) : (
                            <>
                                <h3 style={{ marginBottom: '4px', color: 'var(--text-title)', fontWeight: 600 }}>
                                    {processingComplete ? 'Processing Complete!' : 'AI Processing...'}
                                </h3>
                                {processingComplete && (
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>You can rename the file below before opening it.</p>
                                )}
                                <form onSubmit={handleRenameSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%' }}>
                                    <label style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)' }}>File name:</label>
                                    <input
                                        type="text"
                                        className="text-input"
                                        value={renameValue}
                                        onChange={e => setRenameValue(e.target.value)}
                                        autoFocus
                                    />
                                    <button type="submit" className="btn-primary" style={{ padding: '10px' }}>Save Name</button>
                                    {processingComplete ? (
                                        <button
                                            type="button"
                                            onClick={handleGoToReview}
                                            className="btn-primary"
                                            style={{ padding: '10px', background: 'linear-gradient(135deg, #10b981, #059669)', boxShadow: '0 4px 12px rgba(16,185,129,0.3)' }}
                                        >
                                            Open Review →
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={handleCancelProcessing}
                                            className="btn-outline"
                                            style={{ padding: '10px', borderColor: 'var(--danger-light)', color: 'var(--danger)' }}
                                        >
                                            Cancel Processing
                                        </button>
                                    )}
                                </form>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Modal Overlay for Gmail Integration Explanation */}
            {showConnectModal && (
                <div className="modal-overlay" style={{ zIndex: 1000 }}>
                    <div className="modal-content" style={{ maxWidth: '500px', width: '90%', textAlign: 'left', padding: '32px' }}>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-title)', marginBottom: '12px' }}>
                            Connect Gmail Inbox
                        </h2>
                        <p style={{ color: 'var(--text-secondary)', fontSize: '15px', marginBottom: '24px', lineHeight: 1.5 }}>
                            Enable fully automated background ingestion for your business invoices.
                        </p>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginBottom: '32px' }}>
                            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                <div style={{
                                    background: 'rgba(59, 130, 246, 0.1)',
                                    color: 'var(--accent)',
                                    padding: '10px',
                                    borderRadius: '10px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}>
                                    <Search size={20} />
                                </div>
                                <div>
                                    <h4 style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-title)', marginBottom: '4px' }}>Secure Inbox Monitoring</h4>
                                    <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                        Sits securely in your mail looking specifically for unread invoice attachments.
                                    </p>
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                <div style={{
                                    background: 'rgba(59, 130, 246, 0.1)',
                                    color: 'var(--accent)',
                                    padding: '10px',
                                    borderRadius: '10px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}>
                                    <Activity size={20} />
                                </div>
                                <div>
                                    <h4 style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-title)', marginBottom: '4px' }}>Automatic AI Workflows</h4>
                                    <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                        Once a matching invoice is detected, the OCR extraction and validation workflow runs automatically.
                                    </p>
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                                <div style={{
                                    background: 'rgba(59, 130, 246, 0.1)',
                                    color: 'var(--accent)',
                                    padding: '10px',
                                    borderRadius: '10px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}>
                                    <FileSpreadsheet size={20} />
                                </div>
                                <div>
                                    <h4 style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-title)', marginBottom: '4px' }}>Instant Spreadsheet Export</h4>
                                    <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                                        Automatically parses all data and syncs details directly to Excel and Google Sheets.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                            <button
                                onClick={() => setShowConnectModal(false)}
                                className="btn-outline"
                                style={{ padding: '10px 20px', minWidth: '100px' }}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => {
                                    setShowConnectModal(false);
                                    handleConnectGoogle();
                                }}
                                className="btn-primary"
                                style={{ padding: '10px 24px', minWidth: '150px' }}
                            >
                                Authorize & Connect
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
