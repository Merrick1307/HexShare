import {
  Document,
  DocumentAnalytics,
  DocumentGroup,
  DownloadUrlResponse,
  ExternalRoomContext,
  ExternalRoomDocumentSession,
  ExternalRoomGrant,
  ExternalRoomInviteInspection,
  ExternalRoomSession,
  ActivityItem,
  NdaAcceptPayload,
  NdaAcceptanceRecord,
  NdaPolicyAdminView,
  NdaPolicySummary,
  NdaStatus,
  PaginatedResponse,
  WorkspaceSummary,
  ProvisionExternalRoomAccessResponse,
  ShareInspection,
  ShareLink,
  ViewSession,
} from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || import.meta.env.VITE_APP_URL || '').replace(/\/$/, '');
const API_PREFIX = `${API_BASE_URL}/api/v1`;
const AUTH_PREFIX = `${API_BASE_URL}/api/v1`;

type UploadInitResponse = {
  document_id: string;
  object_key: string;
  method?: string;
  upload_url: string;
  required_headers?: Record<string, string>;
  required_form_fields?: Record<string, string>;
};

type CreateDocumentInput = {
  name: string;
  mime_type: string;
  size: number;
  storage_key: string;
};

function toAbsoluteApiUrl(pathOrUrl: string) {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return `${API_BASE_URL}${pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`}`;
}

function toAbsoluteFrontendUrl(pathOrUrl: string) {
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  return `${window.location.origin}${pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`}`;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail;
      if (typeof detail === 'string') throw new Error(detail);
    }
    const text = await response.text();
    throw new Error(text || `HTTP error ${response.status}`);
  }

  if (response.status === 204) return null as T;

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json() as Promise<T>;

  return response.text() as T;
}

let isRefreshing = false;
let refreshPromise: Promise<boolean> | null = null;

async function tryRefreshToken(): Promise<boolean> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }
  isRefreshing = true;
  refreshPromise = (async () => {
    try {
      const response = await fetch(`${AUTH_PREFIX}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json' },
      });
      if (response.ok) {
        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

async function fetchWithAuth<T>(url: string, options: RequestInit = {}, retried = false): Promise<T> {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  });

  if (response.status === 401 && !retried) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return fetchWithAuth<T>(url, options, true);
    }
    window.location.href = `${AUTH_PREFIX}/auth/login`;
    throw new Error('Session expired. Redirecting to login...');
  }

  return parseResponse<T>(response);
}

async function fetchPublic<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  });
  return parseResponse<T>(response);
}

async function fetchExternal<T>(url: string, options: RequestInit = {}, retried = false): Promise<T> {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  });

  if (response.status === 401 && !retried) {
    const refreshed = await fetch(`${API_PREFIX}/external-room/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (refreshed.ok) {
      return fetchExternal<T>(url, options, true);
    }
  }

  return parseResponse<T>(response);
}

async function fetchExternalResponse(url: string, options: RequestInit = {}, retried = false): Promise<Response> {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    credentials: 'include',
    headers: {
      Accept: '*/*',
      ...options.headers,
    },
  });

  if (response.status === 401 && !retried) {
    const refreshed = await fetch(`${API_PREFIX}/external-room/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (refreshed.ok) {
      return fetchExternalResponse(url, options, true);
    }
  }

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail;
      if (typeof detail === 'string') throw new Error(detail);
    }
    const text = await response.text().catch(() => '');
    throw new Error(text || `HTTP error ${response.status}`);
  }

  return response;
}

export const api = {
  get loginUrl() {
    return `${AUTH_PREFIX}/auth/login`;
  },

  get signupUrl() {
    return `${AUTH_PREFIX}/auth/signup`;
  },

  async logout(): Promise<void> {
    await fetch(`${AUTH_PREFIX}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    window.location.href = '/';
  },

  async refreshToken(): Promise<boolean> {
    return tryRefreshToken();
  },

  async authConfig(): Promise<{ demo_mode: boolean; default_idp: string }> {
    return fetchPublic<{ demo_mode: boolean; default_idp: string }>(`${AUTH_PREFIX}/auth/config`);
  },

  async demoLogin(): Promise<void> {
    const response = await fetch(`${AUTH_PREFIX}/auth/demo-login`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error('Demo login is not available on this deployment.');
    }
  },

  toAbsoluteApiUrl,
  toAbsoluteFrontendUrl,

  async listDocuments(offset = 0, limit = 20): Promise<PaginatedResponse<Document>> {
    return fetchWithAuth<PaginatedResponse<Document>>(`${API_PREFIX}/documents?offset=${offset}&limit=${limit}`);
  },

  async getDocument(documentId: string): Promise<Document> {
    return fetchWithAuth<Document>(`${API_PREFIX}/documents/${documentId}`);
  },

  async createDocument(data: CreateDocumentInput): Promise<Document> {
    const params = new URLSearchParams({
      name: data.name,
      mime_type: data.mime_type,
      size: data.size.toString(),
      storage_key: data.storage_key,
    });
    return fetchWithAuth<Document>(`${API_PREFIX}/documents?${params.toString()}`, { method: 'POST' });
  },

  async deleteDocument(documentId: string): Promise<void> {
    return fetchWithAuth<void>(`${API_PREFIX}/documents/${documentId}`, { method: 'DELETE' });
  },

  async moveDocumentToGroup(documentId: string, groupId: string | null): Promise<Document> {
    const params = groupId ? `?group_id=${encodeURIComponent(groupId)}` : '';
    return fetchWithAuth<Document>(`${API_PREFIX}/documents/${documentId}/group${params}`, { method: 'PATCH' });
  },

  async initiateUpload(file: File): Promise<UploadInitResponse> {
    return fetchWithAuth<UploadInitResponse>(`${API_PREFIX}/uploads/initiate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
        size: file.size,
      }),
    });
  },

  async completeUpload(payload: {
    document_id: string;
    object_key: string;
    name: string;
    mime_type: string;
    size: number;
  }): Promise<Document> {
    return fetchWithAuth<Document>(`${API_PREFIX}/uploads/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  async uploadFileDirect(file: File, init: UploadInitResponse): Promise<void> {
    if (init.required_form_fields && Object.keys(init.required_form_fields).length > 0) {
      const formData = new FormData();
      Object.entries(init.required_form_fields).forEach(([key, value]) => formData.append(key, value));
      formData.append('file', file);
      const response = await fetch(init.upload_url, { method: 'POST', body: formData, cache: 'no-store' });
      await parseResponse(response);
      return;
    }

    const response = await fetch(init.upload_url, {
      method: init.method || 'PUT',
      cache: 'no-store',
      headers: {
        'Content-Type': file.type || 'application/octet-stream',
        ...(init.required_headers || {}),
      },
      body: file,
    });
    await parseResponse(response);
  },

  async listLinks(documentId?: string, offset = 0, limit = 20): Promise<PaginatedResponse<ShareLink>> {
    const url = documentId
      ? `${API_PREFIX}/documents/${documentId}/links?offset=${offset}&limit=${limit}`
      : `${API_PREFIX}/links?offset=${offset}&limit=${limit}`;
    return fetchWithAuth<PaginatedResponse<ShareLink>>(url);
  },

  async createLink(
    documentId: string,
    data: {
      expires_in_days: number;
      can_download: boolean;
      can_print: boolean;
      require_email: boolean;
      allowed_emails: string[];
      recipient_email?: string;
      recipient_display_name?: string;
    }
  ): Promise<ShareLink> {
    const params = new URLSearchParams();
    params.append('expires_in', Math.max(1, data.expires_in_days * 24 * 60 * 60).toString());
    if (data.can_download) params.append('can_download', 'true');
    if (data.can_print) params.append('can_print', 'true');
    if (data.require_email) params.append('require_email', 'true');
    data.allowed_emails.forEach((email) => params.append('allowed_emails', email));
    if (data.recipient_email?.trim()) params.append('recipient_email', data.recipient_email.trim());
    if (data.recipient_display_name?.trim()) params.append('recipient_display_name', data.recipient_display_name.trim());

    return fetchWithAuth<ShareLink>(`${API_PREFIX}/documents/${documentId}/links?${params.toString()}`, {
      method: 'POST',
    });
  },

  async revokeLink(linkId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/links/${linkId}/revoke`, { method: 'POST' });
  },

  async getAnalytics(documentId: string): Promise<DocumentAnalytics> {
    return fetchWithAuth<DocumentAnalytics>(`${API_PREFIX}/documents/${documentId}/analytics`);
  },

  async inspectShareLink(token: string): Promise<ShareInspection> {
    return fetchPublic<ShareInspection>(`${API_PREFIX}/view/${token}`);
  },

  async createViewSession(token: string, email?: string): Promise<ViewSession> {
    return fetchPublic<ViewSession>(`${API_PREFIX}/view/${token}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email || null }),
    });
  },

  async fetchViewerContent(path: string): Promise<Response> {
    const response = await fetch(toAbsoluteApiUrl(path), {
      method: 'GET',
      cache: 'no-store',
    });
    if (!response.ok) {
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const payload = await response.json().catch(() => null);
        const detail = payload?.detail;
        if (typeof detail === 'string') throw new Error(detail);
      }
      const text = await response.text().catch(() => '');
      throw new Error(text || `HTTP error ${response.status}`);
    }
    return response;
  },

  async getWorkspaceSummary(): Promise<WorkspaceSummary> {
    return fetchWithAuth<WorkspaceSummary>(`${API_PREFIX}/workspace/summary`);
  },

  async getActivity(limit = 50): Promise<ActivityItem[]> {
    return fetchWithAuth<ActivityItem[]>(`${API_PREFIX}/activity?limit=${limit}`);
  },

  async listNdaPolicies(): Promise<NdaPolicySummary[]> {
    return fetchWithAuth<NdaPolicySummary[]>(`${API_PREFIX}/nda/policies`);
  },

  async getShareNda(sessionId: string): Promise<NdaStatus[]> {
    return fetchPublic<NdaStatus[]>(`${API_PREFIX}/view-sessions/${sessionId}/nda`);
  },

  async acceptShareNda(sessionId: string, payload: NdaAcceptPayload): Promise<void> {
    await fetchPublic<void>(`${API_PREFIX}/view-sessions/${sessionId}/nda/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  shareNdaPdfUrl(sessionId: string, scopeType: string, scopeId: string): string {
    return `${API_PREFIX}/view-sessions/${sessionId}/nda/pdf?scope_type=${encodeURIComponent(scopeType)}&scope_id=${encodeURIComponent(scopeId)}`;
  },

  async getDocumentNda(documentId: string): Promise<NdaPolicyAdminView | null> {
    return fetchWithAuth<NdaPolicyAdminView | null>(`${API_PREFIX}/documents/${documentId}/nda`);
  },
  async setDocumentNdaText(documentId: string, data: { title?: string; text_body: string; require_scroll: boolean; require_typed_signature: boolean }): Promise<NdaPolicyAdminView> {
    return fetchWithAuth<NdaPolicyAdminView>(`${API_PREFIX}/documents/${documentId}/nda`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
  },
  async setDocumentNdaPdf(documentId: string, file: File, opts: { title?: string; require_scroll: boolean; require_typed_signature: boolean }): Promise<NdaPolicyAdminView> {
    const form = new FormData();
    form.append('pdf', file);
    if (opts.title) form.append('title', opts.title);
    form.append('require_scroll', String(opts.require_scroll));
    form.append('require_typed_signature', String(opts.require_typed_signature));
    return fetchWithAuth<NdaPolicyAdminView>(`${API_PREFIX}/documents/${documentId}/nda/pdf`, { method: 'POST', body: form });
  },
  async deleteDocumentNda(documentId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/documents/${documentId}/nda`, { method: 'DELETE' });
  },
  async listDocumentNdaAcceptances(documentId: string): Promise<NdaAcceptanceRecord[]> {
    return fetchWithAuth<NdaAcceptanceRecord[]>(`${API_PREFIX}/documents/${documentId}/nda/acceptances`);
  },

  async getGroupNda(groupId: string): Promise<NdaPolicyAdminView | null> {
    return fetchWithAuth<NdaPolicyAdminView | null>(`${API_PREFIX}/document-groups/${groupId}/nda`);
  },
  async setGroupNdaText(groupId: string, data: { title?: string; text_body: string; require_scroll: boolean; require_typed_signature: boolean }): Promise<NdaPolicyAdminView> {
    return fetchWithAuth<NdaPolicyAdminView>(`${API_PREFIX}/document-groups/${groupId}/nda`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
  },
  async setGroupNdaPdf(groupId: string, file: File, opts: { title?: string; require_scroll: boolean; require_typed_signature: boolean }): Promise<NdaPolicyAdminView> {
    const form = new FormData();
    form.append('pdf', file);
    if (opts.title) form.append('title', opts.title);
    form.append('require_scroll', String(opts.require_scroll));
    form.append('require_typed_signature', String(opts.require_typed_signature));
    return fetchWithAuth<NdaPolicyAdminView>(`${API_PREFIX}/document-groups/${groupId}/nda/pdf`, { method: 'POST', body: form });
  },
  async deleteGroupNda(groupId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/document-groups/${groupId}/nda`, { method: 'DELETE' });
  },
  async listGroupNdaAcceptances(groupId: string): Promise<NdaAcceptanceRecord[]> {
    return fetchWithAuth<NdaAcceptanceRecord[]>(`${API_PREFIX}/document-groups/${groupId}/nda/acceptances`);
  },

  async sendPageView(sessionId: string, pageNumber: number): Promise<void> {
    await fetchPublic<void>(`${API_PREFIX}/view-sessions/${sessionId}/page-view?page_number=${pageNumber}`, {
      method: 'POST',
    });
  },

  async closeViewSession(sessionId: string): Promise<void> {
    await fetchPublic<void>(`${API_PREFIX}/view-sessions/${sessionId}/close`, { method: 'POST' });
  },

  async listGroups(offset = 0, limit = 20): Promise<PaginatedResponse<DocumentGroup>> {
    return fetchWithAuth<PaginatedResponse<DocumentGroup>>(`${API_PREFIX}/document-groups?offset=${offset}&limit=${limit}`);
  },

  async createGroup(data: { name: string; description?: string }): Promise<DocumentGroup> {
    const params = new URLSearchParams({ name: data.name });
    if (data.description) params.append('description', data.description);
    return fetchWithAuth<DocumentGroup>(`${API_PREFIX}/document-groups?${params.toString()}`, { method: 'POST' });
  },

  async getGroup(groupId: string): Promise<DocumentGroup> {
    return fetchWithAuth<DocumentGroup>(`${API_PREFIX}/document-groups/${groupId}`);
  },

  async updateGroup(groupId: string, data: { name?: string; description?: string }): Promise<DocumentGroup> {
    return fetchWithAuth<DocumentGroup>(`${API_PREFIX}/document-groups/${groupId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async deleteGroup(groupId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/document-groups/${groupId}`, { method: 'DELETE' });
  },

  async listGroupDocuments(groupId: string): Promise<Document[]> {
    return fetchWithAuth<Document[]>(`${API_PREFIX}/document-groups/${groupId}/documents`);
  },

  async createDocumentInGroup(
    groupId: string,
    data: { name: string; mime_type: string; size: number; storage_key: string }
  ): Promise<Document> {
    const params = new URLSearchParams({
      name: data.name,
      mime_type: data.mime_type,
      size: data.size.toString(),
      storage_key: data.storage_key,
    });
    return fetchWithAuth<Document>(`${API_PREFIX}/document-groups/${groupId}/documents?${params.toString()}`, {
      method: 'POST',
    });
  },

  async addGroupMember(groupId: string, userId: string, role: 'member' | 'owner' = 'member'): Promise<{ status: string; user_id: string; role: string }> {
    const params = new URLSearchParams({ user_id: userId, role });
    return fetchWithAuth<{ status: string; user_id: string; role: string }>(`${API_PREFIX}/document-groups/${groupId}/members?${params.toString()}`, { method: 'POST' });
  },

  async removeGroupMember(groupId: string, userId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/document-groups/${groupId}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' });
  },

  async listExternalRoomAccess(groupId: string): Promise<ExternalRoomGrant[]> {
    return fetchWithAuth<ExternalRoomGrant[]>(`${API_PREFIX}/document-groups/${groupId}/external-access`);
  },

  async provisionExternalRoomAccess(
    groupId: string,
    data: {
      recipient_email: string;
      recipient_display_name?: string;
      can_download: boolean;
      can_print: boolean;
      expires_in?: number;
      invite_expires_in?: number;
    }
  ): Promise<ProvisionExternalRoomAccessResponse> {
    const params = new URLSearchParams();
    params.append('recipient_email', data.recipient_email.trim());
    if (data.recipient_display_name?.trim()) params.append('recipient_display_name', data.recipient_display_name.trim());
    if (data.can_download) params.append('can_download', 'true');
    if (data.can_print) params.append('can_print', 'true');
    if (typeof data.expires_in === 'number') params.append('expires_in', String(data.expires_in));
    if (typeof data.invite_expires_in === 'number') params.append('invite_expires_in', String(data.invite_expires_in));
    return fetchWithAuth<ProvisionExternalRoomAccessResponse>(
      `${API_PREFIX}/document-groups/${groupId}/external-access?${params.toString()}`,
      { method: 'POST' }
    );
  },

  async revokeExternalRoomAccess(groupId: string, grantId: string): Promise<void> {
    await fetchWithAuth<void>(`${API_PREFIX}/document-groups/${groupId}/external-access/${encodeURIComponent(grantId)}`, {
      method: 'DELETE',
    });
  },

  async inspectExternalRoomInvite(token: string): Promise<ExternalRoomInviteInspection> {
    return fetchPublic<ExternalRoomInviteInspection>(`${API_PREFIX}/external-room/invitations/${encodeURIComponent(token)}`);
  },

  async createExternalRoomSession(token: string, email: string): Promise<ExternalRoomSession> {
    return fetchPublic<ExternalRoomSession>(`${API_PREFIX}/external-room/invitations/${encodeURIComponent(token)}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
  },

  async getExternalRoomContext(): Promise<ExternalRoomContext> {
    return fetchExternal<ExternalRoomContext>(`${API_PREFIX}/external-room/current`);
  },

  async listExternalRoomDocuments(): Promise<Document[]> {
    return fetchExternal<Document[]>(`${API_PREFIX}/external-room/current/documents`);
  },

  async getExternalRoomNda(documentId?: string): Promise<NdaStatus[]> {
    const q = documentId ? `?document_id=${encodeURIComponent(documentId)}` : '';
    return fetchExternal<NdaStatus[]>(`${API_PREFIX}/external-room/current/nda${q}`);
  },

  async acceptExternalRoomNda(payload: NdaAcceptPayload): Promise<void> {
    await fetchExternal<void>(`${API_PREFIX}/external-room/current/nda/accept`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  externalRoomNdaPdfUrl(scopeType: string, scopeId: string): string {
    return `${API_PREFIX}/external-room/current/nda/pdf?scope_type=${encodeURIComponent(scopeType)}&scope_id=${encodeURIComponent(scopeId)}`;
  },

  async getExternalRoomDocumentDownload(documentId: string, expiresIn = 900): Promise<DownloadUrlResponse> {
    return fetchExternal<DownloadUrlResponse>(
      `${API_PREFIX}/external-room/current/documents/${encodeURIComponent(documentId)}/download?expires_in=${expiresIn}`
    );
  },

  async createExternalRoomDocumentSession(documentId: string): Promise<ExternalRoomDocumentSession> {
    return fetchExternal<ExternalRoomDocumentSession>(
      `${API_PREFIX}/external-room/current/documents/${encodeURIComponent(documentId)}/sessions`,
      { method: 'POST' }
    );
  },

  async getExternalRoomDocumentSession(sessionId: string): Promise<ExternalRoomDocumentSession> {
    return fetchExternal<ExternalRoomDocumentSession>(
      `${API_PREFIX}/external-room/view-sessions/${encodeURIComponent(sessionId)}`
    );
  },

  async fetchExternalRoomViewerContent(path: string): Promise<Response> {
    return fetchExternalResponse(toAbsoluteApiUrl(path));
  },

  async closeExternalRoomDocumentSession(sessionId: string): Promise<void> {
    await fetchExternal<void>(`${API_PREFIX}/external-room/view-sessions/${encodeURIComponent(sessionId)}/close`, {
      method: 'POST',
    });
  },

  async recordExternalRoomPageView(sessionId: string, pageNumber: number): Promise<void> {
    await fetchExternal<void>(
      `${API_PREFIX}/external-room/view-sessions/${encodeURIComponent(sessionId)}/page-view?page_number=${pageNumber}`,
      { method: 'POST' }
    );
  },

  async logoutExternalRoom(): Promise<void> {
    await fetchExternal<void>(`${API_PREFIX}/external-room/logout`, { method: 'POST' });
  },

  async listWorkspaceUsers(page: number = 1, pageSize: number = 20, search?: string): Promise<{
    users: Array<{ id: string; user_id?: string; email?: string; name?: string; username?: string }>;
    total: number;
    page: number;
    page_size: number;
  }> {
    const params = new URLSearchParams({ page: page.toString(), page_size: pageSize.toString() });
    if (search) params.set('search', search);
    return fetchWithAuth<{
      users: Array<{ id: string; user_id?: string; email?: string; name?: string; username?: string }>;
      total: number;
      page: number;
      page_size: number;
    }>(`${API_PREFIX}/workspace/users?${params.toString()}`);
  },
};
