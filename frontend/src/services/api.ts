import { Document, DocumentAnalytics, DocumentGroup, ShareInspection, ShareLink, ViewSession } from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || import.meta.env.VITE_APP_URL || '').replace(/\/$/, '');
const API_PREFIX = `${API_BASE_URL}/api/v1`;
const AUTH_PREFIX = `${API_BASE_URL}/api`;

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

async function parseResponse(response: Response) {
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

  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();

  return response.text();
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

async function fetchWithAuth(url: string, options: RequestInit = {}, retried = false): Promise<unknown> {
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
      return fetchWithAuth(url, options, true);
    }
    window.location.href = `${AUTH_PREFIX}/auth/login`;
    throw new Error('Session expired. Redirecting to login...');
  }

  return parseResponse(response);
}

async function fetchPublic(url: string, options: RequestInit = {}) {
  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  });
  return parseResponse(response);
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

  toAbsoluteApiUrl,
  toAbsoluteFrontendUrl,

  async listDocuments(): Promise<Document[]> {
    return fetchWithAuth(`${API_PREFIX}/documents`);
  },

  async getDocument(documentId: string): Promise<Document> {
    return fetchWithAuth(`${API_PREFIX}/documents/${documentId}`);
  },

  async createDocument(data: CreateDocumentInput): Promise<Document> {
    const params = new URLSearchParams({
      name: data.name,
      mime_type: data.mime_type,
      size: data.size.toString(),
      storage_key: data.storage_key,
    });
    return fetchWithAuth(`${API_PREFIX}/documents?${params.toString()}`, { method: 'POST' });
  },

  async deleteDocument(documentId: string): Promise<void> {
    return fetchWithAuth(`${API_PREFIX}/documents/${documentId}`, { method: 'DELETE' });
  },

  async moveDocumentToGroup(documentId: string, groupId: string | null): Promise<Document> {
    const params = groupId ? `?group_id=${encodeURIComponent(groupId)}` : '';
    return fetchWithAuth(`${API_PREFIX}/documents/${documentId}/group${params}`, { method: 'PATCH' });
  },

  async initiateUpload(file: File): Promise<UploadInitResponse> {
    return fetchWithAuth(`${API_PREFIX}/uploads/initiate`, {
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
    return fetchWithAuth(`${API_PREFIX}/uploads/complete`, {
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

  async listLinks(documentId?: string): Promise<ShareLink[]> {
    const url = documentId ? `${API_PREFIX}/documents/${documentId}/links` : `${API_PREFIX}/links`;
    return fetchWithAuth(url);
  },

  async createLink(
    documentId: string,
    data: {
      expires_in_days: number;
      can_download: boolean;
      can_print: boolean;
      require_email: boolean;
      allowed_emails: string[];
    }
  ): Promise<ShareLink> {
    const params = new URLSearchParams();
    params.append('expires_in', Math.max(1, data.expires_in_days * 24 * 60 * 60).toString());
    if (data.can_download) params.append('can_download', 'true');
    if (data.can_print) params.append('can_print', 'true');
    if (data.require_email) params.append('require_email', 'true');
    data.allowed_emails.forEach((email) => params.append('allowed_emails', email));

    return fetchWithAuth(`${API_PREFIX}/documents/${documentId}/links?${params.toString()}`, {
      method: 'POST',
    });
  },

  async revokeLink(linkId: string): Promise<void> {
    await fetchWithAuth(`${API_PREFIX}/links/${linkId}/revoke`, { method: 'POST' });
  },

  async getAnalytics(documentId: string): Promise<DocumentAnalytics> {
    return fetchWithAuth(`${API_PREFIX}/documents/${documentId}/analytics`);
  },

  async inspectShareLink(token: string): Promise<ShareInspection> {
    return fetchPublic(`${API_PREFIX}/view/${token}`);
  },

  async createViewSession(token: string, email?: string): Promise<ViewSession> {
    return fetchPublic(`${API_PREFIX}/view/${token}/sessions`, {
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

  async sendViewerHeartbeat(sessionId: string, payload: { page_number?: number; duration_ms?: number } = {}): Promise<void> {
    await fetchPublic(`${API_PREFIX}/view-sessions/${sessionId}/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  async closeViewSession(sessionId: string): Promise<void> {
    await fetchPublic(`${API_PREFIX}/view-sessions/${sessionId}/close`, { method: 'POST' });
  },

  async listGroups(): Promise<DocumentGroup[]> {
    return fetchWithAuth(`${API_PREFIX}/document-groups`);
  },

  async createGroup(data: { name: string; description?: string }): Promise<DocumentGroup> {
    const params = new URLSearchParams({ name: data.name });
    if (data.description) params.append('description', data.description);
    return fetchWithAuth(`${API_PREFIX}/document-groups?${params.toString()}`, { method: 'POST' });
  },

  async getGroup(groupId: string): Promise<DocumentGroup> {
    return fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}`);
  },

  async updateGroup(groupId: string, data: { name?: string; description?: string }): Promise<DocumentGroup> {
    return fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  async deleteGroup(groupId: string): Promise<void> {
    await fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}`, { method: 'DELETE' });
  },

  async listGroupDocuments(groupId: string): Promise<Document[]> {
    return fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}/documents`);
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
    return fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}/documents?${params.toString()}`, {
      method: 'POST',
    });
  },

  async addGroupMember(groupId: string, userId: string, role: 'member' | 'owner' = 'member'): Promise<{ status: string; user_id: string; role: string }> {
    const params = new URLSearchParams({ user_id: userId, role });
    return fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}/members?${params.toString()}`, { method: 'POST' });
  },

  async removeGroupMember(groupId: string, userId: string): Promise<void> {
    await fetchWithAuth(`${API_PREFIX}/document-groups/${groupId}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' });
  },

  async listWorkspaceUsers(page: number = 1, pageSize: number = 20, search?: string): Promise<{
    users: Array<{ id: string; user_id?: string; email?: string; name?: string; username?: string }>;
    total: number;
    page: number;
    page_size: number;
  }> {
    const params = new URLSearchParams({ page: page.toString(), page_size: pageSize.toString() });
    if (search) params.set('search', search);
    return fetchWithAuth(`${API_PREFIX}/workspace/users?${params.toString()}`);
  },
};
