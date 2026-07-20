import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { MoreHorizontal, Search, Upload, FileText, Link2, Eye, FolderInput, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import { Document, DocumentGroup, ShareLink } from '../types';
import { formatBytes } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { WorkspaceStats } from '../components/WorkspaceStats';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';

function DocumentRowMenu({
  doc,
  isOpen,
  onToggle,
  onCreateLink,
  onMoveToGroup,
  onDelete,
}: {
  doc: Document;
  isOpen: boolean;
  onToggle: () => void;
  onCreateLink: (document: Document) => void;
  onMoveToGroup: (document: Document) => void;
  onDelete: (document: Document) => void;
}) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuContentRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setPos(null);
      return;
    }
    const update = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (rect) setPos({ top: rect.bottom + 8, left: rect.right - 192 }); // 192px = w-48
    };
    update();
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || menuContentRef.current?.contains(target)) return;
      onToggle();
    }
    document.addEventListener('mousedown', handleClick);
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [isOpen, onToggle]);

  return (
    <div className="relative inline-block text-left">
      <Button ref={buttonRef} type="button" variant="outline" size="sm" className="h-9 w-9 p-0" onClick={onToggle}>
        <MoreHorizontal className="h-4 w-4" />
      </Button>
      {isOpen && pos
        ? createPortal(
            <div
              ref={menuContentRef}
              style={{ position: 'fixed', top: pos.top, left: pos.left }}
              className="z-50 w-48 rounded-xl border border-zinc-200 bg-white p-1 shadow-xl"
            >
              <Link to={`/documents/${doc.id}`} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50">
                <Eye className="h-4 w-4" />
                View details
              </Link>
              <button
                type="button"
                onClick={() => onCreateLink(doc)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50"
              >
                <Link2 className="h-4 w-4" />
                Create link
              </button>
              <button
                type="button"
                onClick={() => onMoveToGroup(doc)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50"
              >
                <FolderInput className="h-4 w-4" />
                Move to room
              </button>
              <div className="my-1 border-t border-zinc-100" />
              <button
                type="button"
                onClick={() => onDelete(doc)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

type LinkDraft = {
  expires_in_days: number;
  can_download: boolean;
  can_print: boolean;
  require_email: boolean;
  allowed_emails: string;
};

const DEFAULT_LINK_DRAFT: LinkDraft = {
  expires_in_days: 7,
  can_download: false,
  can_print: false,
  require_email: false,
  allowed_emails: '',
};

function truncateMiddle(value: string, start = 18, end = 10) {
  if (value.length <= start + end + 3) return value;
  return `${value.slice(0, start)}...${value.slice(-end)}`;
}

function compactShareUrl(value: string) {
  try {
    const url = new URL(value);
    const parts = url.pathname.split('/').filter(Boolean);
    const token = parts[parts.length - 1] || '';
    if (parts[0] === 'view' && token) {
      return `${url.origin}/view/${truncateMiddle(token, 10, 8)}`;
    }
    return `${url.origin}${truncateMiddle(url.pathname, 20, 10)}`;
  } catch {
    return truncateMiddle(value, 28, 12);
  }
}

export function Dashboard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const {
    items: documents,
    total: docTotal,
    isLoading: docsLoading,
    hasMore: docsHasMore,
    sentinelRef: docSentinelRef,
    reset: resetDocs,
    setItems: setDocuments,
  } = useInfiniteScroll<Document>({
    fetchFn: (offset, limit) => api.listDocuments(offset, limit),
    pageSize: 20,
    rootRef: containerRef,
  });

  const [links, setLinks] = useState<ShareLink[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isCreateLinkModalOpen, setIsCreateLinkModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [createLinkError, setCreateLinkError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [linkDraft, setLinkDraft] = useState<LinkDraft>(DEFAULT_LINK_DRAFT);
  const [lastCreatedLink, setLastCreatedLink] = useState<ShareLink | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [groups, setGroups] = useState<DocumentGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [isMoveModalOpen, setIsMoveModalOpen] = useState(false);
  const [moveTargetGroupId, setMoveTargetGroupId] = useState<string>('');
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);

  const refreshDocuments = useCallback(async () => {
    resetDocs();
    return [];
  }, [resetDocs]);

  const refreshLinks = useCallback(async () => {
    try {
      const resp = await api.listLinks(undefined, 0, 100);
      setLinks(resp.items);
    } catch {
      // keep the document list usable even when link aggregation fails
    }
  }, []);

  const refreshGroups = useCallback(async () => {
    try {
      const resp = await api.listGroups(0, 100);
      setGroups(resp.items);
    } catch {
      // Rooms are optional, don't block on failure.
    }
  }, []);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      await Promise.all([refreshDocuments(), refreshLinks(), refreshGroups()]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to load documents');
    } finally {
      setIsLoading(false);
    }
  }, [refreshDocuments, refreshLinks, refreshGroups]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (!successMessage) return;
    const timer = window.setTimeout(() => setSuccessMessage(null), 3500);
    return () => window.clearTimeout(timer);
  }, [successMessage]);

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setUploadError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);

    const formData = new FormData(e.currentTarget);
    const file = formData.get('file') as File | null;

    if (!file) {
      setUploadError('Select a file first.');
      setIsSubmitting(false);
      return;
    }

    try {
      const uploadInit = await api.initiateUpload(file);
      await api.uploadFileDirect(file, uploadInit);

      let uploadedDocument: Document;
      if (selectedGroupId) {
        // Upload to the selected room.
        uploadedDocument = await api.createDocumentInGroup(selectedGroupId, {
          name: file.name,
          mime_type: file.type || 'application/octet-stream',
          size: file.size,
          storage_key: uploadInit.object_key,
        });
      } else {
        // Upload without assigning a room.
        uploadedDocument = await api.completeUpload({
          document_id: uploadInit.document_id,
          object_key: uploadInit.object_key,
          name: file.name,
          mime_type: file.type || 'application/octet-stream',
          size: file.size,
        });
      }

      setDocuments((current) => {
        const withoutExisting = current.filter((doc) => doc.id !== uploadedDocument.id);
        return [uploadedDocument, ...withoutExisting];
      });
      setIsUploadModalOpen(false);
      setSelectedGroupId('');
      e.currentTarget.reset();
      setSuccessMessage('Document uploaded successfully.');

      void refreshDocuments();
      void refreshLinks();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Failed to upload document');
    } finally {
      setIsSubmitting(false);
    }
  }

  function openCreateLinkModal(document: Document) {
    setOpenMenuId(null);
    setSelectedDocument(document);
    setIsCreateLinkModalOpen(true);
    setActionError(null);
    setCreateLinkError(null);
    setLastCreatedLink(null);
    setLinkDraft(DEFAULT_LINK_DRAFT);
  }

  async function handleCreateLink(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!selectedDocument) return;
    setActionError(null);
    setCreateLinkError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);
    try {
      const link = await api.createLink(selectedDocument.id, {
        expires_in_days: linkDraft.expires_in_days,
        can_download: linkDraft.can_download,
        can_print: linkDraft.can_print,
        require_email: linkDraft.require_email,
        allowed_emails: linkDraft.allowed_emails
          .split(',')
          .map((email) => email.trim())
          .filter(Boolean),
      });
      setLastCreatedLink(link);
      setSuccessMessage(`Share link created for ${selectedDocument.name}.`);
      await loadData();
    } catch (error) {
      setCreateLinkError(error instanceof Error ? error.message : 'Failed to create link');
    } finally {
      setIsSubmitting(false);
    }
  }

  function openMoveModal(document: Document) {
    setOpenMenuId(null);
    setSelectedDocument(document);
    setMoveTargetGroupId(document.room_id || '');
    setIsMoveModalOpen(true);
    setActionError(null);
  }

  async function handleMoveToGroup() {
    if (!selectedDocument) return;
    setActionError(null);
    setIsSubmitting(true);
    try {
      const targetGroupId = moveTargetGroupId || null;
      await api.moveDocumentToGroup(selectedDocument.id, targetGroupId);
      setIsMoveModalOpen(false);
      setSelectedDocument(null);
      setSuccessMessage(targetGroupId ? 'Document moved to room.' : 'Document removed from room.');
      await loadData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to move document');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setOpenMenuId(null);
    setActionError(null);
    setIsSubmitting(true);
    try {
      await api.deleteDocument(deleteTarget.id);
      setSuccessMessage(`"${deleteTarget.name}" deleted.`);
      setDeleteTarget(null);
      await loadData();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to delete document');
    } finally {
      setIsSubmitting(false);
    }
  }

  const filteredDocuments = useMemo(
    () => documents.filter((doc) => doc.name.toLowerCase().includes(searchQuery.toLowerCase())),
    [documents, searchQuery]
  );

  const linksByDocument = useMemo(() => {
    return links.reduce<Record<string, ShareLink[]>>((acc, link) => {
      acc[link.document_id] = [...(acc[link.document_id] || []), link];
      return acc;
    }, {});
  }, [links]);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">Documents</h1>
          <p className="mt-1 text-sm text-zinc-500">Manage documents, generate share links, and inspect analytics.</p>
        </div>
        <Button onClick={() => setIsUploadModalOpen(true)} className="gap-2">
          <Upload className="h-4 w-4" />
          Upload Document
        </Button>
      </div>

      {successMessage ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{successMessage}</div> : null}
      {actionError ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{actionError}</div> : null}

      <WorkspaceStats />

      <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-center">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
          <Input placeholder="Search documents..." className="pl-9" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
        </div>
        <div className="text-sm text-zinc-500">{docTotal} document{docTotal === 1 ? '' : 's'}</div>
      </div>

      <div ref={containerRef} className="overflow-y-auto rounded-xl border border-zinc-200 bg-white shadow-sm max-h-[calc(100vh-16rem)]">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="px-6 py-4">Name</th>
              <th className="px-6 py-4">Size</th>
              <th className="px-6 py-4">Uploaded</th>
              <th className="px-6 py-4">Links</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {isLoading && documents.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-zinc-500">Loading documents...</td></tr>
            ) : filteredDocuments.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-zinc-500">
                  <div className="flex flex-col items-center justify-center">
                    <FileText className="mb-3 h-10 w-10 text-zinc-300" />
                    <p className="text-base font-medium text-zinc-900">No documents found</p>
                    <p className="mt-1 text-sm">Upload a document to get started.</p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredDocuments.map((doc) => {
                const docLinks = linksByDocument[doc.id] || [];
                const activeLinks = docLinks.filter((link) => !link.revoked_at && new Date(link.expires_at) > new Date()).length;
                return (
                  <tr key={doc.id} className="group transition-colors hover:bg-zinc-50/50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600"><FileText className="h-5 w-5" /></div>
                        <div>
                          <Link to={`/documents/${doc.id}`} className="font-medium text-zinc-900 hover:text-indigo-600 hover:underline">{doc.name}</Link>
                          <p className="mt-0.5 text-xs text-zinc-500">{doc.mime_type || 'application/octet-stream'}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-zinc-600">{formatBytes(doc.size)}</td>
                    <td className="px-6 py-4 text-zinc-600">{format(new Date(doc.created_at), 'MMM d, yyyy')}</td>
                    <td className="px-6 py-4">
                      {docLinks.length > 0 ? (
                        <div className="flex items-center gap-2">
                          <Badge variant={activeLinks > 0 ? 'success' : 'neutral'}>{activeLinks} active</Badge>
                          <span className="text-xs text-zinc-500">{docLinks.length} total</span>
                        </div>
                      ) : (
                        <span className="text-xs text-zinc-400">No links yet</span>
                      )}
                    </td>
                    <td className="relative overflow-visible px-6 py-4 text-right">
                      <DocumentRowMenu
                        doc={doc}
                        isOpen={openMenuId === doc.id}
                        onToggle={() => setOpenMenuId((current) => current === doc.id ? null : doc.id)}
                        onCreateLink={openCreateLinkModal}
                        onMoveToGroup={openMoveModal}
                        onDelete={(document) => {
                          setOpenMenuId(null);
                          setDeleteTarget(document);
                        }}
                      />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        <div ref={docSentinelRef} className="h-1" />
        {docsLoading && documents.length > 0 ? (
          <div className="px-6 py-3 text-center text-sm text-zinc-400">Loading more documents...</div>
        ) : null}
      </div>

      <Modal isOpen={isUploadModalOpen} onClose={() => { setIsUploadModalOpen(false); setSelectedGroupId(''); }} title="Upload Document">
        <form onSubmit={handleUpload} className="space-y-6">
          {uploadError ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{uploadError}</div> : null}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Select File</label>
            <Input type="file" name="file" required />
          </div>
          {groups.length > 0 && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900">Add to Room (optional)</label>
              <select
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                value={selectedGroupId}
                onChange={(e) => setSelectedGroupId(e.target.value)}
              >
                <option value="">No room (personal documents)</option>
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>{g.name}</option>
                ))}
              </select>
              <p className="text-xs text-zinc-500">Optionally assign this document to a room for shared access.</p>
            </div>
          )}
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => { setIsUploadModalOpen(false); setSelectedGroupId(''); }}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Uploading...' : 'Upload'}</Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={isCreateLinkModalOpen}
        onClose={() => {
          setIsCreateLinkModalOpen(false);
          setCreateLinkError(null);
        }}
        title="Create share link"
      >
        <form onSubmit={handleCreateLink} className="space-y-6">
          {createLinkError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {createLinkError}
            </div>
          ) : null}
          <div><label className="text-sm font-medium text-zinc-900">Expiry (days)</label><Input type="number" min={1} max={365} value={linkDraft.expires_in_days} onChange={(e) => setLinkDraft((current) => ({ ...current, expires_in_days: Number(e.target.value) || 1 }))} className="mt-1.5" /></div>
          <div className="space-y-3">
            <label className="text-sm font-medium text-zinc-900">Permissions</label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={linkDraft.can_download} onChange={(e) => setLinkDraft((current) => ({ ...current, can_download: e.target.checked }))} /><span>Allow download</span></label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={linkDraft.can_print} onChange={(e) => setLinkDraft((current) => ({ ...current, can_print: e.target.checked }))} /><span>Allow print</span></label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={linkDraft.require_email} onChange={(e) => setLinkDraft((current) => ({ ...current, require_email: e.target.checked }))} /><span>Require email</span></label>
          </div>
          <div><label className="text-sm font-medium text-zinc-900">Allowed emails</label><Input className="mt-1.5" placeholder="client@acme.com, approver@corp.io" value={linkDraft.allowed_emails} onChange={(e) => setLinkDraft((current) => ({ ...current, allowed_emails: e.target.value }))} /></div>
          {lastCreatedLink ? (
            <button
              type="button"
              title={api.toAbsoluteFrontendUrl(lastCreatedLink.share_path)}
              onClick={() => void navigator.clipboard.writeText(api.toAbsoluteFrontendUrl(lastCreatedLink.share_path))}
              className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-3 text-left text-sm text-indigo-900"
            >
              <span className="min-w-0 truncate font-mono">{compactShareUrl(api.toAbsoluteFrontendUrl(lastCreatedLink.share_path))}</span>
              <span className="text-xs font-medium">Copy</span>
            </button>
          ) : null}
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setIsCreateLinkModalOpen(false);
                setCreateLinkError(null);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Creating...' : 'Create link'}</Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={isMoveModalOpen} onClose={() => setIsMoveModalOpen(false)} title="Move to Room">
        <div className="space-y-6">
          {actionError && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</div>}
          {selectedDocument && (
            <div className="rounded-lg bg-zinc-50 px-4 py-3">
              <p className="text-sm font-medium text-zinc-900">{selectedDocument.name}</p>
              <p className="text-xs text-zinc-500">{selectedDocument.room_id ? 'Currently in a room' : 'Not in any room'}</p>
            </div>
          )}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Select Target Room</label>
            <select
              className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              value={moveTargetGroupId}
              onChange={(e) => setMoveTargetGroupId(e.target.value)}
            >
              <option value="">No room (personal documents)</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setIsMoveModalOpen(false)}>Cancel</Button>
            <Button type="button" onClick={handleMoveToGroup} disabled={isSubmitting}>
              {isSubmitting ? 'Moving...' : 'Move'}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete document"
        description={
          deleteTarget
            ? `Delete "${deleteTarget.name}"? This action cannot be undone.`
            : ''
        }
        confirmLabel="Delete"
        isConfirming={isSubmitting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
