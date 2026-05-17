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
  revoked_at: string | null;
  created_at: string;
  created_by: string;
  share_token: string;
  share_path: string;
}

export interface DocumentAnalytics {
  unique_visitors: number;
  total_views: number;
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
