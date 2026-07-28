import type { DocumentProtection } from '../types';

export const ACCEPTED_DOCUMENT_EXTENSIONS = [
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
  '.txt', '.csv', '.md', '.png', '.jpg', '.jpeg', '.webp',
] as const;

export const ACCEPTED_DOCUMENTS_ATTRIBUTE = ACCEPTED_DOCUMENT_EXTENSIONS.join(',');
export const MAX_BULK_UPLOAD_FILES = 20;
export const BULK_UPLOAD_CONCURRENCY = 3;

const PROTECTED_PREVIEW = new Set(['.txt', '.csv', '.md', '.png', '.jpg', '.jpeg', '.webp']);
const extensionFor = (name: string) => `.${name.split('.').pop()?.toLowerCase() || ''}`;

export function isAcceptedDocument(file: File): boolean {
  return (ACCEPTED_DOCUMENT_EXTENSIONS as readonly string[]).includes(extensionFor(file.name));
}

export function estimateProtection(file: File): DocumentProtection {
  const extension = extensionFor(file.name);
  if (extension === '.pdf') {
    return {
      profile: 'strongest',
      label: 'Strongest protection',
      inline_view_supported: true,
      watermark_mode: 'pixel_baked',
      page_activity: true,
      download_required: false,
      reason: null,
    };
  }
  if (PROTECTED_PREVIEW.has(extension)) {
    return {
      profile: 'protected_preview',
      label: 'Protected preview',
      inline_view_supported: true,
      watermark_mode: 'rendered',
      page_activity: false,
      download_required: false,
      reason: null,
    };
  }
  return {
    profile: 'download_only',
    label: 'Download only',
    inline_view_supported: false,
    watermark_mode: null,
    page_activity: false,
    download_required: true,
    reason: 'inline_view_not_supported',
  };
}

export const SUPPORTED_DOCUMENT_MESSAGE =
  'For the strongest protection, use PDF. PDF pages are streamed through a recipient-watermarked viewer with page-level activity. Other accepted formats may use a protected preview or require a controlled download.';
