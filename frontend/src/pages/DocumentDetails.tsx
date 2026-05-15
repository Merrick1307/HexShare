import React, { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { format } from 'date-fns';
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  Link as LinkIcon,
  Printer,
  Trash2,
  Users,
} from 'lucide-react';
import { api } from '../services/api';
import { Document, ShareLink, DocumentAnalytics } from '../types';
import { formatBytes } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';

function statusForLink(link: ShareLink) {
  if (link.revoked_at) return { label: 'Revoked', variant: 'danger' as const };
  if (new Date(link.expires_at) <= new Date()) return { label: 'Expired', variant: 'warning' as const };
  return { label: 'Active', variant: 'success' as const };
}

export function DocumentDetails() {
  const { id } = useParams<{ id: string }>();
  const [document, setDocument] = useState<Document | null>(null);
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [analytics, setAnalytics] = useState<DocumentAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreateLinkModalOpen, setIsCreateLinkModalOpen] = useState(false);
  const [copiedValue, setCopiedValue] = useState<string | null>(null);
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [canDownload, setCanDownload] = useState(false);
  const [canPrint, setCanPrint] = useState(false);
  const [requireEmail, setRequireEmail] = useState(false);
  const [allowedEmails, setAllowedEmails] = useState('');
  const [pageError, setPageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [infoMessage, setInfoMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (id) void loadData(id);
  }, [id]);

  useEffect(() => {
    if (!infoMessage) return;
    const timer = window.setTimeout(() => setInfoMessage(null), 3500);
    return () => window.clearTimeout(timer);
  }, [infoMessage]);

  async function loadData(docId: string) {
    setIsLoading(true);
    setPageError(null);
    try {
      const [doc, docAnalytics, docLinks] = await Promise.all([
        api.getDocument(docId),
        api.getAnalytics(docId),
        api.listLinks(docId),
      ]);
      setDocument(doc);
      setAnalytics(docAnalytics);
      setLinks(docLinks);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : 'Failed to load document details');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreateLink(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!id) return;
    setActionError(null);
    setIsSubmitting(true);
    try {
      const link = await api.createLink(id, {
        expires_in_days: expiresInDays,
        can_download: canDownload,
        can_print: canPrint,
        require_email: requireEmail,
        allowed_emails: allowedEmails.split(',').map((value) => value.trim()).filter(Boolean),
      });
      setLinks((current) => [link, ...current]);
      setIsCreateLinkModalOpen(false);
      setInfoMessage(`Link ${link.id} created.`);
      setExpiresInDays(7);
      setCanDownload(false);
      setCanPrint(false);
      setRequireEmail(false);
      setAllowedEmails('');
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to create link');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRevokeLink(linkId: string) {
    if (!id) return;
    setActionError(null);
    try {
      await api.revokeLink(linkId);
      await loadData(id);
      setInfoMessage(`Link ${linkId} revoked.`);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Failed to revoke link');
    }
  }

  async function copyToClipboard(value: string) {
    await navigator.clipboard.writeText(value);
    setCopiedValue(value);
    window.setTimeout(() => setCopiedValue(null), 1500);
  }

  const activeCount = useMemo(() => links.filter((link) => !link.revoked_at && new Date(link.expires_at) > new Date()).length, [links]);

  if (isLoading) return <div className="flex h-64 items-center justify-center text-zinc-500">Loading document details...</div>;
  if (pageError) return <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700"><p className="font-medium">Could not load this document.</p><p className="mt-1 text-sm">{pageError}</p></div>;
  if (!document) return <div className="flex h-64 items-center justify-center text-zinc-500">Document not found.</div>;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <Link to="/dashboard" className="text-zinc-400 transition-colors hover:text-zinc-900"><ArrowLeft className="h-5 w-5" /></Link>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">{document.name}</h1>
          <p className="mt-1 text-sm text-zinc-500">Uploaded {format(new Date(document.created_at), 'MMM d, yyyy')} · {formatBytes(document.size)}</p>
        </div>
      </div>

      {infoMessage ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{infoMessage}</div> : null}
      {actionError ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{actionError}</div> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-4">
            <div>
              <CardTitle>Share links</CardTitle>
              <CardDescription>Server-backed share links with revocation-aware viewer sessions.</CardDescription>
            </div>
            <Button onClick={() => setIsCreateLinkModalOpen(true)} size="sm" className="gap-2"><LinkIcon className="h-4 w-4" />Create link</Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-500">
              <Badge variant={activeCount > 0 ? 'success' : 'neutral'}>{activeCount} active</Badge>
              <span>{links.length} total</span>
            </div>

            {links.length === 0 ? (
              <div className="rounded-xl border border-dashed border-zinc-200 px-6 py-10 text-center text-sm text-zinc-500">No share links yet for this document.</div>
            ) : (
              <div className="space-y-3">
                {links.map((link) => {
                  const status = statusForLink(link);
                  const shareUrl = api.toAbsoluteFrontendUrl(link.share_path);
                  return (
                    <div key={link.id} className="rounded-xl border border-zinc-200 bg-zinc-50/60 p-4">
                      <div className="flex flex-col gap-4">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                          <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium text-zinc-900">Link ID</span>
                              <code className="rounded bg-white px-2 py-0.5 text-xs text-zinc-700">{link.id}</code>
                              <Badge variant={status.variant}>{status.label}</Badge>
                            </div>
                            <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                              <span>Expires {format(new Date(link.expires_at), 'MMM d, yyyy h:mm a')}</span>
                              {link.can_download ? <Badge variant="neutral">Download</Badge> : null}
                              {link.can_print ? <Badge variant="neutral">Print</Badge> : null}
                              {link.require_email ? <Badge variant="neutral">Email required</Badge> : null}
                              {link.allowed_emails.length > 0 ? <Badge variant="neutral">{link.allowed_emails.length} allowed emails</Badge> : null}
                            </div>
                            <div className="text-xs text-zinc-500">Share URL: <span className="break-all font-mono">{shareUrl}</span></div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" size="sm" onClick={() => void copyToClipboard(shareUrl)}>
                              {copiedValue === shareUrl ? <CheckCircle2 className="mr-2 h-4 w-4 text-emerald-600" /> : <Copy className="mr-2 h-4 w-4" />}Copy
                            </Button>
                            <Button type="button" variant="outline" size="sm" onClick={() => window.open(shareUrl, '_blank', 'noopener,noreferrer')}>
                              <ExternalLink className="mr-2 h-4 w-4" />Open
                            </Button>
                            {!link.revoked_at ? <Button type="button" variant="danger" size="sm" className="gap-2" onClick={() => void handleRevokeLink(link.id)}><Trash2 className="h-4 w-4" />Revoke</Button> : null}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Analytics</CardTitle><CardDescription>Document engagement from the backend analytics API.</CardDescription></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-4"><div className="flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600"><Eye className="h-6 w-6" /></div><div><p className="text-2xl font-semibold text-zinc-950">{analytics?.total_views ?? 0}</p><p className="text-sm font-medium text-zinc-500">Total views</p></div></div>
              <div className="flex items-center gap-4"><div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><Users className="h-6 w-6" /></div><div><p className="text-2xl font-semibold text-zinc-950">{analytics?.unique_visitors ?? 0}</p><p className="text-sm font-medium text-zinc-500">Unique visitors</p></div></div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Metadata</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm text-zinc-600">
              <div><p className="font-medium text-zinc-900">Document ID</p><code className="block rounded bg-zinc-50 px-2 py-1 text-xs">{document.id}</code></div>
              <div><p className="font-medium text-zinc-900">Storage key</p><code className="block break-all rounded bg-zinc-50 px-2 py-1 text-xs">{document.storage_key}</code></div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Modal isOpen={isCreateLinkModalOpen} onClose={() => setIsCreateLinkModalOpen(false)} title="Create share link">
        <form onSubmit={handleCreateLink} className="space-y-6">
          <div><label className="text-sm font-medium text-zinc-900">Expiry (days)</label><Input type="number" min={1} max={365} value={expiresInDays} onChange={(e) => setExpiresInDays(Number(e.target.value) || 1)} className="mt-1.5" /></div>
          <div className="space-y-3">
            <label className="text-sm font-medium text-zinc-900">Permissions</label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={canDownload} onChange={(e) => setCanDownload(e.target.checked)} /><span className="inline-flex items-center gap-2"><Download className="h-4 w-4" /> Allow download</span></label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={canPrint} onChange={(e) => setCanPrint(e.target.checked)} /><span className="inline-flex items-center gap-2"><Printer className="h-4 w-4" /> Allow print</span></label>
            <label className="flex items-center gap-3 text-sm text-zinc-700"><input type="checkbox" checked={requireEmail} onChange={(e) => setRequireEmail(e.target.checked)} /><span className="inline-flex items-center gap-2"><Users className="h-4 w-4" /> Require email</span></label>
          </div>
          <div><label className="text-sm font-medium text-zinc-900">Allowed emails</label><Input className="mt-1.5" placeholder="client@acme.com, approver@corp.io" value={allowedEmails} onChange={(e) => setAllowedEmails(e.target.value)} /></div>
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4"><Button type="button" variant="outline" onClick={() => setIsCreateLinkModalOpen(false)}>Cancel</Button><Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Creating...' : 'Create link'}</Button></div>
        </form>
      </Modal>
    </div>
  );
}
