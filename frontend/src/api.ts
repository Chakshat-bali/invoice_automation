// Base API URL - allow override via env var for Vercel deployment
export const API_URL = import.meta.env.VITE_API_URL || "";

export interface Invoice {
    invoice_id: string;
    original_filename: string;
    vendor_name: string | null;
    total_amount: number | null;
    status: string;
    created_at: string;
    [key: string]: any;
}

export async function fetchInvoices(status?: string, vendor?: string): Promise<Invoice[]> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (vendor) params.append('vendor', vendor);
    
    let url = `${API_URL}/invoices`;
    if (params.toString()) url += `?${params.toString()}`;
    
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to fetch invoices");
    return await response.json();
}


export function getExcelExportUrl(status?: string): string {
  const params = new URLSearchParams();
  if (status) params.append("status", status);

  const query = params.toString();
  return `${API_URL}/export/excel${query ? `?${query}` : ""}`;
}



export async function fetchInvoice(id: string): Promise<Invoice> {
    const response = await fetch(`${API_URL}/invoices/${id}`);
    if (!response.ok) throw new Error("Failed to load invoice");
    return await response.json();
}

export async function uploadInvoice(file: File): Promise<{invoice_id: string, original_filename: string}> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${API_URL}/invoices/upload`, {
        method: 'POST',
        body: formData
    });
    
    if (!response.ok) {
        const err = await response.text();
        throw new Error(err || 'Upload failed');
    }
    
    return await response.json();
}

export async function deleteInvoice(id: string): Promise<void> {
    const response = await fetch(`${API_URL}/invoices/${id}`, { method: 'DELETE' });
    if (!response.ok) throw new Error('Failed to delete invoice');
}

export async function updateInvoice(id: string, updates: Partial<Invoice>): Promise<Invoice> {
    const response = await fetch(`${API_URL}/invoices/${id}/fields`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ field_updates: updates })
    });
    
    if (!response.ok) throw new Error('Failed to update invoice');
    return await response.json();
}

export async function approveInvoice(id: string): Promise<Invoice> {
    const response = await fetch(`${API_URL}/invoices/${id}/approve`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ reviewed_by: 'reviewer' })
    });
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to approve invoice');
    }
    return await response.json();
}

export async function fetchSheetsLink(): Promise<{url: string | null}> {
    const response = await fetch(`${API_URL}/export/sheets/link`);
    if (!response.ok) throw new Error('Failed to get sheet link');
    return await response.json();
}

export async function pollEmailInbox(): Promise<{processed: number}> {
    const response = await fetch(`${API_URL}/email/poll`, { method: 'POST' });
    if (!response.ok) throw new Error('Failed to poll email inbox');
    return await response.json();
}

export interface AuditLogEntry {
    field_name: string;
    old_value: any;
    new_value: any;
    changed_by: string;
    changed_at: string;
    action: string;
}

export async function fetchAuditLog(id: string): Promise<AuditLogEntry[]> {
    const response = await fetch(`${API_URL}/invoices/${id}/audit-log`);
    if (!response.ok) throw new Error('Failed to fetch audit log');
    return await response.json();
}

export interface GoogleAuthStatus {
    connected: boolean;
    email: string | null;
}

export async function fetchGoogleAuthStatus(): Promise<GoogleAuthStatus> {
    const response = await fetch(`${API_URL}/auth/google/status`);
    if (!response.ok) throw new Error('Failed to fetch Google auth status');
    return await response.json();
}

export async function disconnectGoogleAuth(): Promise<void> {
    const response = await fetch(`${API_URL}/auth/google/disconnect`, { method: 'POST' });
    if (!response.ok) throw new Error('Failed to disconnect Google account');
}

export async function fetchGoogleAuthUrl(): Promise<{url: string}> {
    const response = await fetch(`${API_URL}/auth/google/url`);
    if (!response.ok) throw new Error('Failed to fetch Google auth URL');
    return await response.json();
}
