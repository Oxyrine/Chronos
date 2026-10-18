import type {
  UserSession,
  SystemHealth,
  Finding,
  RankedFinding,
  ShelflifePrediction,
  ExposureResponse,
  ProposalRecord,
  VerificationResult,
  Attestation,
  LedgerChainVerification,
} from './types/contracts';

let lastNegotiatedCurve: string | null = null;

export function getLastNegotiatedCurve(): string | null {
  return lastNegotiatedCurve;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, {
    ...options,
    credentials: 'same-origin',
    headers,
  });

  const curveHeader = response.headers.get('x-tls-group');
  if (curveHeader) {
    lastNegotiatedCurve = curveHeader;
  }

  if (response.status === 401) {
    if (!path.includes('/api/auth/login')) {
      // Broadcast session expiration
      window.dispatchEvent(new CustomEvent('chronos:unauthorized'));
    }
    const errBody = await response.json().catch(() => ({ detail: 'Authentication required' }));
    throw new ApiError(401, errBody.detail || 'Authentication required');
  }

  if (response.status === 403) {
    const errBody = await response.json().catch(() => ({ detail: 'Secops (security_engineer) role required' }));
    throw new ApiError(403, errBody.detail || 'Secops (security_engineer) role required');
  }

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, errBody.detail || response.statusText);
  }

  return response.json();
}

export const api = {
  // Auth
  async login(username: string, password: string): Promise<UserSession> {
    return request<UserSession>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  async logout(): Promise<{ status: string }> {
    return request<{ status: string }>('/api/auth/logout', { method: 'POST' });
  },

  async me(): Promise<UserSession> {
    return request<UserSession>('/api/auth/me');
  },

  // Health & Metrics
  async getHealth(): Promise<SystemHealth> {
    return request<SystemHealth>('/health');
  },

  async getMetrics(): Promise<any> {
    return request<any>('/api/metrics');
  },

  // Inventory
  async startScan(): Promise<{ scan_id: string }> {
    return request<{ scan_id: string }>('/api/scan', { method: 'POST' });
  },

  async getScanStatus(scanId: string): Promise<{ scan_id: string; status: string; findings?: number; scan_seconds?: number }> {
    return request(`/api/scan/${scanId}`);
  },

  async getFindings(status?: string, service?: string): Promise<Finding[]> {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (service) params.set('service', service);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return request<Finding[]>(`/api/findings${qs}`);
  },

  async getCbom(): Promise<any> {
    return request<any>('/api/cbom');
  },

  // Shelf-life
  async runShelflife(): Promise<{ job_id: string; columns: number }> {
    return request<{ job_id: string; columns: number }>('/api/shelflife/run', { method: 'POST' });
  },

  async getShelflife(): Promise<ShelflifePrediction[]> {
    return request<ShelflifePrediction[]>('/api/shelflife');
  },

  async overrideShelflife(table: string, column: string, category: string, reason: string): Promise<any> {
    return request<any>(`/api/shelflife/${encodeURIComponent(table)}/${encodeURIComponent(column)}/override`, {
      method: 'POST',
      body: JSON.stringify({ category, reason }),
    });
  },

  // Exposure & Mosca
  async getExposure(scenario: string = 'base_2033'): Promise<ExposureResponse> {
    return request<ExposureResponse>(`/api/exposure?scenario=${encodeURIComponent(scenario)}`);
  },

  async getPriorities(scenario: string = 'base_2033'): Promise<RankedFinding[]> {
    return request<RankedFinding[]>(`/api/priorities?scenario=${encodeURIComponent(scenario)}`);
  },

  // Remediation
  async createProposal(findingId: string, mode: 'compatibility' | 'strict' = 'compatibility'): Promise<ProposalRecord> {
    return request<ProposalRecord>('/api/proposals', {
      method: 'POST',
      body: JSON.stringify({ finding_id: findingId, mode }),
    });
  },

  async listProposals(): Promise<ProposalRecord[]> {
    return request<ProposalRecord[]>('/api/proposals');
  },

  async getProposal(proposalId: string): Promise<ProposalRecord> {
    return request<ProposalRecord>(`/api/proposals/${encodeURIComponent(proposalId)}`);
  },

  async verifyProposal(proposalId: string): Promise<{ proposal_id: string; status: string }> {
    return request<{ proposal_id: string; status: string }>(`/api/proposals/${encodeURIComponent(proposalId)}/verify`, {
      method: 'POST',
    });
  },

  async getVerification(proposalId: string): Promise<VerificationResult> {
    return request<VerificationResult>(`/api/verifications/${encodeURIComponent(proposalId)}`);
  },

  async approveProposal(proposalId: string): Promise<any> {
    return request<any>(`/api/proposals/${encodeURIComponent(proposalId)}/approve`, {
      method: 'POST',
    });
  },

  // Ledger
  async getLedger(): Promise<Attestation[]> {
    return request<Attestation[]>('/api/ledger');
  },

  async verifyLedger(): Promise<LedgerChainVerification> {
    return request<LedgerChainVerification>('/api/ledger/verify');
  },

  async getPublicKey(): Promise<{ public_key: string }> {
    return request<{ public_key: string }>('/api/ledger/public-key');
  },
};
