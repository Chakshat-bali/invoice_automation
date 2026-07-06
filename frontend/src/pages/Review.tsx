import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { type Invoice, fetchInvoice, updateInvoice, approveInvoice, fetchSheetsLink, API_URL, getSessionId, getExcelExportUrl } from '../api';
import { 
    FileText, 
    Building2, 
    ListChecks, 
    DollarSign, 
    AlertCircle, 
    Sparkles, 
    ArrowLeft, 
    Save, 
    CheckCircle,
    FileSpreadsheet,
    ChevronDown,
    ExternalLink
} from 'lucide-react';
import './Review.css';

export default function Review() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [invoice, setInvoice] = useState<Invoice | null>(null);
    const [formData, setFormData] = useState<any>({});
    const [lineItems, setLineItems] = useState<any[]>([]);
    const [activeTab, setActiveTab] = useState('entities');
    const [isSaving, setIsSaving] = useState(false);
    const [isApproving, setIsApproving] = useState(false);
    const [blobUrl, setBlobUrl] = useState<string | null>(null);
    const [showExportDropdown, setShowExportDropdown] = useState(false);
    const exportDropdownRef = useRef<HTMLDivElement>(null);
    const [sheetsUrl, setSheetsUrl] = useState<string | null>(null);
    const [showApprovedBanner, setShowApprovedBanner] = useState(false);
    const [approvalBanner, setApprovalBanner] = useState<{ type: 'success' | 'warning'; message: string }>({
        type: 'success',
        message: 'Invoice approved and synced to Google Sheets!'
    });

    // Auto-dismiss the approval banner after 4 seconds
    useEffect(() => {
        if (!showApprovedBanner) return;
        const t = setTimeout(() => setShowApprovedBanner(false), 4000);
        return () => clearTimeout(t);
    }, [showApprovedBanner]);

    useEffect(() => {
        if (id) loadInvoice(id);
        fetchSheetsLink()
            .then(res => setSheetsUrl(res.url))
            .catch(err => console.error("Error getting sheet link", err));
    }, [id]);

    // Close export dropdown on outside click
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (exportDropdownRef.current && !exportDropdownRef.current.contains(e.target as Node)) {
                setShowExportDropdown(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    useEffect(() => {
        if (!invoice?.invoice_id) return;
        let currentObjectUrl = "";
        const url = `${API_URL}/invoices/${invoice.invoice_id}/file`;
        fetch(url, { 
            headers: { 
                'ngrok-skip-browser-warning': 'true',
                'X-Session-ID': getSessionId()
            } 
        })
            .then(res => res.blob())
            .then(blob => {
                currentObjectUrl = URL.createObjectURL(blob);
                setBlobUrl(currentObjectUrl);
            })
            .catch(err => console.error("Failed to load file blob", err));
        
        return () => {
            if (currentObjectUrl) {
                URL.revokeObjectURL(currentObjectUrl);
            }
        };
    }, [invoice?.invoice_id]);

    async function loadInvoice(invoiceId: string) {
        try {
            const data = await fetchInvoice(invoiceId);
            setInvoice(data);
            
            // Extract core fields
            setFormData({
                vendor_name: data.vendor_name || '',
                vendor_address: data.vendor_address || '',
                customer_name: data.customer_name || '',
                customer_address: data.customer_address || '',
                invoice_number: data.invoice_number || '',
                invoice_date: data.invoice_date || '',
                due_date: data.due_date || '',
                subtotal: data.subtotal || '',
                tax_amount: data.tax_amount || '',
                total_amount: data.total_amount || ''
            });

            // Parse line items
            let items = [];
            try {
                if (data.line_items) {
                    items = Array.isArray(data.line_items) ? data.line_items : [];
                }
            } catch (e) {
                console.error("Failed to parse line items", e);
            }
            setLineItems(items);
        } catch (error) {
            alert('Failed to load invoice');
            navigate('/');
        }
    }

    const handleFormChange = (field: string, value: string) => {
        setFormData((prev: any) => ({ ...prev, [field]: value }));
    };

    const handleLineItemChange = (index: number, field: string, value: string) => {
        const newItems = [...lineItems];
        newItems[index] = { ...newItems[index], [field]: value };
        setLineItems(newItems);
    };

    const handleSave = async () => {
        if (!invoice) return;
        setIsSaving(true);
        try {
            const updates = {
                ...formData,
                line_items: lineItems
            };
            const updated = await updateInvoice(invoice.invoice_id, updates);
            setInvoice(updated);
            alert('Changes saved successfully');
        } catch (error) {
            alert('Failed to save changes');
        } finally {
            setIsSaving(false);
        }
    };

    const handleApprove = async () => {
        if (!invoice) return;
        if (hasError) {
            alert("Please resolve the validation error(s) before approving.");
            return;
        }
        setIsApproving(true);
        try {
            const result = await approveInvoice(invoice.invoice_id);
            setInvoice(result.invoice);
            setActiveTab('entities');
            const sheetsResult = result.export_results?.sheets;
            if (sheetsResult === 'success') {
                setApprovalBanner({
                    type: 'success',
                    message: 'Invoice approved and synced to Google Sheets!'
                });
            } else {
                setApprovalBanner({
                    type: 'warning',
                    message: `Invoice approved, but Google Sheets export did not complete: ${sheetsResult || 'not configured'}`
                });
            }
            setShowApprovedBanner(true);
        } catch (error) {
            alert((error as Error).message);
        } finally {
            setIsApproving(false);
        }
    };

    if (!invoice) {
        return <div style={{ padding: '40px', textAlign: 'center' }}>Loading invoice...</div>;
    }

    const fileUrl = `${API_URL}/invoices/${invoice.invoice_id}/file?session_id=${getSessionId()}`;
    const displayUrl = blobUrl || fileUrl;
    const isPdf = invoice.original_filename?.toLowerCase().endsWith('.pdf');


    const hasError = invoice.validation_status === 'flagged';


    return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            {/* Approval success banner */}
            {showApprovedBanner && (
                <div style={{
                    position: 'fixed',
                    top: '80px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    zIndex: 999,
                    background: approvalBanner.type === 'success' ? 'linear-gradient(135deg, #10b981, #059669)' : 'linear-gradient(135deg, #f59e0b, #d97706)',
                    color: 'white',
                    padding: '14px 28px',
                    borderRadius: '12px',
                    boxShadow: approvalBanner.type === 'success' ? '0 8px 24px rgba(16,185,129,0.35)' : '0 8px 24px rgba(245,158,11,0.35)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    fontWeight: 600,
                    fontSize: '15px',
                    animation: 'fadeUp 0.3s ease-out',
                }}>
                    {approvalBanner.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
                    {approvalBanner.message}
                    <button
                        onClick={() => setShowApprovedBanner(false)}
                        style={{ all: 'unset', cursor: 'pointer', marginLeft: '8px', opacity: 0.8, fontSize: '18px', lineHeight: 1 }}
                    >×</button>
                </div>
            )}
            <div style={{ padding: '16px 32px', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-card)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {invoice.original_filename}
                    </h1>
                    <span className={`status-pill status-${invoice.status.replace('_', '-')}`}>
                        {invoice.status.replace('_', ' ')}
                    </span>
                </div>
                <div className="header-right" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <button className="btn-outline" style={{ display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => navigate('/')}>
                        <ArrowLeft size={16} /> Back
                    </button>
                </div>
            </div>

            <div className="container" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', padding: '20px 24px', maxWidth: '1800px', margin: '0 auto', flex: 1, width: '100%', minHeight: 0 }}>
                {/* Left Pane - Document Preview */}
                <div className="pane">
                    <div className="pane-header">
                        <FileText size={18} style={{ color: 'var(--accent)' }} />
                        <span>Original Document</span>
                    </div>
                    <div className="pane-content" style={{ padding: '0', overflow: 'hidden', flex: 1, minHeight: 0 }}>
                        <div className="file-preview-container" style={{ height: '100%', minHeight: 'calc(100vh - 250px)', borderRadius: 0, border: 'none' }}>
                            {isPdf ? (
                                <iframe className="file-preview" src={`${displayUrl}#toolbar=0`} title="Invoice PDF" />
                            ) : (
                                <a href={fileUrl} target="_blank" rel="noreferrer" title="Click to open full size">
                                    <img className="file-preview" src={displayUrl} style={{ objectFit: 'contain', cursor: 'zoom-in' }} alt="Invoice" />
                                </a>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right Pane - Form Extraction */}
                <div className="pane">
                    <div className="pane-header">
                        <Sparkles size={18} style={{ color: 'var(--accent)' }} />
                        <span>Extracted Data</span>
                    </div>
                    <div className="pane-content">

                        {invoice.validation_status === 'flagged' && (
                            <div className="banner flagged">
                                <AlertCircle className="banner-icon" size={20} />
                                <div>
                                    <strong>Validation Error Found</strong>
                                    <div style={{ marginTop: '4px', fontWeight: 500, opacity: 0.9 }}>{invoice.validation_notes}</div>
                                </div>
                            </div>
                        )}

                        {invoice.is_duplicate && (
                            <div className="banner flagged" style={{ background: '#fef3c7', borderColor: '#f59e0b', color: '#b45309' }}>
                                <AlertCircle className="banner-icon" size={20} style={{ color: '#d97706' }} />
                                <div>
                                    <strong>Potential Duplicate Invoice</strong>
                                    <div style={{ marginTop: '4px', fontWeight: 500, opacity: 0.9, display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                                        This invoice has been flagged as a potential duplicate.
                                        {invoice.duplicate_of && (
                                            <button 
                                                onClick={() => navigate(`/review/${invoice.duplicate_of}`)} 
                                                className="btn-link"
                                                style={{ background: 'none', border: 'none', color: 'var(--accent)', textDecoration: 'underline', cursor: 'pointer', padding: 0, fontWeight: 700, fontSize: '13.5px' }}
                                            >
                                                View Original Invoice
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        <div className="tabs-header">
                            <button className={`tab-btn ${activeTab === 'entities' ? 'active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => setActiveTab('entities')}>
                                <Building2 size={16} /> Entities
                            </button>
                            <button className={`tab-btn ${activeTab === 'items' ? 'active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => setActiveTab('items')}>
                                <ListChecks size={16} /> Line Items
                            </button>
                            <button className={`tab-btn ${activeTab === 'financials' ? 'active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '8px', border: hasError ? '2px solid #ef4444' : '', color: hasError ? '#ef4444' : '', background: hasError ? '#fef2f2' : '' }} onClick={() => setActiveTab('financials')}>
                                <DollarSign size={16} /> Financials
                            </button>
                            <button className={`tab-btn ${activeTab === 'details' ? 'active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => setActiveTab('details')}>
                                <FileText size={16} /> Details
                            </button>
                        </div>

                        {/* Invoice Details Tab */}
                        {activeTab === 'details' && (
                            <div className="tab-scroll-area">
                                <div className="section-title">Core Metadata</div>
                                <div className="field-group">
                                    <label>Invoice Number</label>
                                    <input value={formData.invoice_number} onChange={e => handleFormChange('invoice_number', e.target.value)} />
                                </div>
                                <div className="field-group">
                                    <label>Invoice Date</label>
                                    <input type="date" value={formData.invoice_date} onChange={e => handleFormChange('invoice_date', e.target.value)} />
                                </div>
                                <div className="field-group">
                                    <label>Due Date</label>
                                    <input type="date" value={formData.due_date} onChange={e => handleFormChange('due_date', e.target.value)} />
                                </div>
                            </div>
                        )}

                        {/* Entities Tab */}
                        {activeTab === 'entities' && (
                            <div className="tab-scroll-area">
                                <div className="section-title">Vendor Info</div>
                                <div className="field-group">
                                    <label>Vendor Name</label>
                                    <input value={formData.vendor_name} onChange={e => handleFormChange('vendor_name', e.target.value)} />
                                </div>
                                <div className="field-group">
                                    <label>Vendor Address</label>
                                    <input value={formData.vendor_address} onChange={e => handleFormChange('vendor_address', e.target.value)} />
                                </div>
                                <div className="section-title" style={{ marginTop: '20px' }}>Customer Info</div>
                                <div className="field-group">
                                    <label>Customer Name</label>
                                    <input value={formData.customer_name} onChange={e => handleFormChange('customer_name', e.target.value)} />
                                </div>
                                <div className="field-group">
                                    <label>Customer Address</label>
                                    <input value={formData.customer_address} onChange={e => handleFormChange('customer_address', e.target.value)} />
                                </div>
                            </div>
                        )}

                        {/* Line Items Tab */}
                        {activeTab === 'items' && (
                            <div className="tab-scroll-area">
                                <div className="section-title">Line Items</div>
                                <div className="line-items">
                                    <table>
                                        <thead>
                                            <tr>
                                                <th>Description</th>
                                                <th style={{ width: '80px' }}>Qty</th>
                                                <th style={{ width: '120px' }}>Unit Price</th>
                                                <th style={{ width: '120px' }}>Total</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {lineItems.map((item, idx) => (
                                                <tr key={idx}>
                                                    <td><input value={item.description || ''} onChange={e => handleLineItemChange(idx, 'description', e.target.value)} /></td>
                                                    <td><input type="number" value={item.quantity || ''} onChange={e => handleLineItemChange(idx, 'quantity', e.target.value)} /></td>
                                                    <td><input type="number" step="0.01" value={item.unit_price || ''} onChange={e => handleLineItemChange(idx, 'unit_price', e.target.value)} /></td>
                                                    <td><input type="number" step="0.01" value={item.line_total || ''} onChange={e => handleLineItemChange(idx, 'line_total', e.target.value)} /></td>
                                                </tr>
                                            ))}
                                            {lineItems.length === 0 && (
                                                <tr><td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-secondary)' }}>No line items extracted.</td></tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Financials Tab */}
                        {activeTab === 'financials' && (
                            <div className="tab-scroll-area">
                                <div className="section-title">Totals</div>
                                <div className="field-group">
                                    <label>Subtotal</label>
                                    <input type="number" step="0.01" value={formData.subtotal} onChange={e => handleFormChange('subtotal', e.target.value)} />
                                </div>
                                <div className="field-group">
                                    <label>Tax Amount</label>
                                    <input type="number" step="0.01" value={formData.tax_amount} onChange={e => handleFormChange('tax_amount', e.target.value)} />
                                </div>
                                <div className="field-group" style={{ background: '#eef2ff', borderColor: '#c7d2fe' }}>
                                    <label style={{ color: 'var(--accent-primary)' }}>Total Amount</label>
                                    <input type="number" step="0.01" style={{ fontWeight: 700, fontSize: '18px' }} value={formData.total_amount} onChange={e => handleFormChange('total_amount', e.target.value)} />
                                </div>
                            </div>
                        )}

                        {invoice.validation_ai_suggestions && (
                            <div className="banner ai-suggestion" style={{ marginTop: '16px' }}>
                                <Sparkles className="banner-icon" size={20} style={{ color: 'var(--accent)' }} />
                                <div className="banner-content">
                                    <strong>AI Resolution Assistant:</strong>
                                    <div style={{ whiteSpace: 'pre-wrap' }}>{invoice.validation_ai_suggestions}</div>
                                </div>
                            </div>
                        )}

                        <div className="actions-footer">
                            <button 
                                className="btn-primary" 
                                style={{ display: 'flex', alignItems: 'center', gap: '8px' }} 
                                onClick={handleSave} 
                                disabled={isSaving}
                            >
                                <Save size={16} /> {isSaving ? 'Saving...' : 'Save Changes'}
                            </button>
                            {invoice.status !== 'approved' ? (
                                <button 
                                    className="btn-approve" 
                                    style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        gap: '8px',
                                        opacity: hasError ? 0.65 : 1,
                                        cursor: hasError ? 'not-allowed' : 'pointer'
                                    }} 
                                    onClick={handleApprove} 
                                    disabled={isApproving}
                                    title={hasError ? 'Please resolve the validation error(s) before approving' : ''}
                                >
                                    <CheckCircle size={16} /> {isApproving ? 'Approving...' : 'Approve & Finalize'}
                                </button>
                            ) : (
                                <div style={{ position: 'relative' }} ref={exportDropdownRef}>
                                    <button 
                                        className="btn-approve" 
                                        style={{ display: 'flex', alignItems: 'center', gap: '8px', position: 'relative' }} 
                                        onClick={() => setShowExportDropdown(!showExportDropdown)}
                                    >
                                        <FileSpreadsheet size={16} /> View in Sheets <ChevronDown size={14} style={{ marginLeft: '2px', transform: showExportDropdown ? 'rotate(0deg)' : 'rotate(180deg)', transition: 'transform 0.2s' }} />
                                    </button>
                                    {showExportDropdown && (
                                        <div style={{
                                            position: 'absolute',
                                            bottom: 'calc(100% + 8px)',
                                            top: 'auto',
                                            right: 0,
                                            background: 'white',
                                            border: '1px solid var(--border-light)',
                                            borderRadius: '8px',
                                            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                                            minWidth: '200px',
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
                                                        transition: 'background 0.2s',
                                                        cursor: 'pointer'
                                                    }}
                                                    onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
                                                    onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                                                >
                                                    <FileSpreadsheet size={16} style={{ color: 'var(--accent)' }} />
                                                    <span style={{ fontSize: '14px', fontWeight: 500 }}>View in Google Sheets</span>
                                                    <ExternalLink size={12} style={{ marginLeft: 'auto', opacity: 0.6 }} />
                                                </a>
                                            )}
                                            <button
                                                onClick={() => {
                                                    window.open(getExcelExportUrl(), '_blank');
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
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
