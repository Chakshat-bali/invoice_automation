import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadInvoice, deleteInvoice, fetchInvoices, type Invoice } from '../api';
import {
    UploadCloud,
    ChevronDown,
    BookOpen,
    Loader2,
    Activity
} from 'lucide-react';
import './Dashboard.css';

export default function Dashboard() {
    const navigate = useNavigate();
    const [invoices, setInvoices] = useState<Invoice[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [isDragOver, setIsDragOver] = useState(false);
    const [processingInvoiceId, setProcessingInvoiceId] = useState<string | null>(null);
    const [processingComplete, setProcessingComplete] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [showGuide, setShowGuide] = useState(true);
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
                    } else if (inv.status !== 'processing') {
                        // Mark complete but keep modal open so user can rename
                        setProcessingComplete(true);
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
    }, []);

    async function loadInvoices() {
        try {
            const data = await fetchInvoices('', '');
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
            alert("Processing cancelled.");
        } catch (error) {
            console.error("Failed to cancel processing", error);
        }
    }

    const total = invoices.length;
    const pending = invoices.filter(i => i.status === 'pending_review').length;
    const approved = invoices.filter(i => i.status === 'approved').length;
    const rejected = invoices.filter(i => i.status === 'rejected').length;

    return (
        <div>
            <div className="hero">
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

            <div className="footer-text">
                Lets Build together
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
                                    <button type="submit" className="btn-primary" style={{ padding: '10px' }}>Save Name</button>
                                </form>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
