export interface PaginatedResponse<T> {
  items: T[];
  total: number;
}

export interface Document {
  id: string;
  tenant_id: string;
  name: string;
  mime_type: string;
  size: number;
  storage_key: string;
  created_at: string;
  created_by: string;
  room_id?: string | null;
  upload_status?: string;
  object_etag?: string | null;
  checksum_sha256?: string | null;
  uploaded_at?: string | null;
}

export interface ShareLink {
  id: string;
  tenant_id: string;
  document_id: string;
  jti: string;
  expires_at: string;
  can_download: boolean;
  can_print: boolean;
  require_email: boolean;
  allowed_emails: string[];
  access_mode?: string;
  bound_email_normalized?: string | null;
  revoked_at: string | null;
  created_at: string;
  created_by: string;
  share_token: string;
  share_path: string;
}

export interface PageAnalytics {
  page_number: number;
  view_count: number;
  total_duration_ms: number;
  avg_duration_ms: number;
}

export interface DocumentAnalytics {
  unique_visitors: number;
  total_views: number;
  total_sessions: number;
  page_views: number;
  total_time_ms: number;
  avg_session_duration_ms: number;
  pages: PageAnalytics[];
}

export interface ShareInspection {
  tenant: string;
  document: string;
  document_name: string;
  mime_type: string;
  size: number;
  link: string;
  permissions: Record<string, boolean>;
  require_email?: boolean;
  allowed_emails?: string[];
  revoked?: boolean;
  expired?: boolean;
}

export interface ViewSession {
  session_id: string;
  tenant_id: string;
  document_id: string;
  document_name: string;
  mime_type: string;
  size: number;
  link_id: string;
  permissions: Record<string, boolean>;
  content_path: string;
  download_path?: string | null;
  events_path: string;
  watermark_text?: string | null;
  inline_view_supported: boolean;
  view_kind: string;
  view_reason?: string | null;
  page_count?: number | null;
  page_image_path_template?: string | null;
}

export interface DocumentGroup {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  created_by: string;
  created_at: string;
}

export interface ExternalRoomGrant {
  grant_id: string;
  external_party_id: string;
  display_name: string | null;
  email: string;
  room_id: string;
  can_download: boolean;
  can_print: boolean;
  revoked_at: string | null;
  expires_at: string | null;
  granted_at: string;
}

export interface ProvisionExternalRoomAccessResponse {
  external_party_id: string;
  display_name: string | null;
  email: string;
  grant_id: string;
  room_id: string;
  invite_token: string;
  invite_path: string;
  invite_expires_at: string;
  can_download: boolean;
  can_print: boolean;
}

export interface ExternalRoomInviteInspection {
  room_id: string;
  room_name: string;
  email: string;
  display_name: string | null;
  can_download: boolean;
  can_print: boolean;
  expires_at: string;
}

export interface ExternalRoomSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
  token_type: string;
  room_id: string;
  room_name: string;
  display_name: string | null;
  email: string;
}

export interface ExternalRoomContext {
  room_id: string;
  room_name: string;
  display_name: string | null;
  email: string;
  can_download: boolean;
  can_print: boolean;
}

export interface ExternalRoomDocumentSession {
  session_id: string;
  tenant_id: string;
  room_id: string;
  document_id: string;
  document_name: string;
  mime_type: string;
  size: number;
  permissions: Record<string, boolean>;
  content_path: string;
  download_path?: string | null;
  watermark_text?: string | null;
  inline_view_supported: boolean;
  view_kind: string;
  view_reason?: string | null;
  page_count?: number | null;
  page_image_path_template?: string | null;
}

export interface DownloadUrlResponse {
  document_id: string;
  download_url: string;
  expires_in: number;
}
