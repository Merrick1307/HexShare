import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { ArrowLeft, Copy, Download, Eye, FolderOpen, LogOut, Mail, Shield } from 'lucide-react';
import { api } from '../services/api';
import { Document, ExternalRoomContext, ExternalRoomInviteInspection } from '../types';
import { formatBytes } from '../lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';

export function ExternalRoomInvitation() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [inspection, setInspection] = useState<ExternalRoomInviteInspection | null>(null);
  const [context, setContext] = useState<ExternalRoomContext | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [copiedValue, setCopiedValue] = useState<string | null>(null);

  const loadSessionData = useCallback(async (): Promise<ExternalRoomContext> => {
    const [nextContext, nextDocuments] = await Promise.all([
      api.getExternalRoomContext(),
      api.listExternalRoomDocuments(),
    ]);
    setContext(nextContext);
    setDocuments(nextDocuments);
    return nextContext;
  }, []);

  const loadPage = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const invite = await api.inspectExternalRoomInvite(token);
      setInspection(invite);
      setEmail(invite.email);

      try {
        const currentContext = await loadSessionData();
        if (currentContext.room_id !== invite.room_id) {
          setContext(null);
          setDocuments([]);
          setInfo(`A different external room session is active for "${currentContext.room_name}". Starting this invitation will replace it.`);
        }
      } catch {
        setContext(null);
        setDocuments([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load invitation');
    } finally {
      setIsLoading(false);
    }
  }, [loadSessionData, token]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    if (!info) return;
    const timer = window.setTimeout(() => setInfo(null), 3000);
    return () => window.clearTimeout(timer);
  }, [info]);

  const activeRoomName = context?.room_name || inspection?.room_name || 'External room';
  const canDownload = context?.can_download || inspection?.can_download || false;
  const inviteUrl = token ? api.toAbsoluteFrontendUrl(`/external-room/invitations/${token}`) : null;

  async function handleCreateSession() {
    if (!token || !email.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await api.createExternalRoomSession(token, email.trim());
      await loadSessionData();
      setInfo('Room session started.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start room session');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDownload(documentId: string) {
    setError(null);
    try {
      const response = await api.getExternalRoomDocumentDownload(documentId);
      window.open(response.download_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to prepare download');
    }
  }

  async function handleOpenViewer(documentId: string) {
    setError(null);
    try {
      const session = await api.createExternalRoomDocumentSession(documentId);
      navigate(`/external-room/viewer/${encodeURIComponent(session.session_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open protected viewer');
    }
  }

  async function handleLogout() {
    setError(null);
    try {
      await api.logoutExternalRoom();
      setContext(null);
      setDocuments([]);
      if (token) {
        const invite = await api.inspectExternalRoomInvite(token);
        setInspection(invite);
        setEmail(invite.email);
      }
      setInfo('Room session closed.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to close room session');
    }
  }

  async function copyToClipboard(value: string) {
    await navigator.clipboard.writeText(value);
    setCopiedValue(value);
    window.setTimeout(() => setCopiedValue(null), 1500);
  }

  const documentCountLabel = useMemo(() => `${documents.length} document${documents.length === 1 ? '' : 's'}`, [documents.length]);

  if (isLoading) {
    return <div className="flex min-h-screen items-center justify-center bg-zinc-50 text-zinc-500">Loading invitation...</div>;
  }

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-center justify-between gap-4">
          <Link to="/" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900">
            <ArrowLeft className="h-4 w-4" />
            Back to HexShare
          </Link>
          {context ? (
            <Button variant="outline" onClick={() => void handleLogout()}>
              <LogOut className="mr-2 h-4 w-4" />
              End session
            </Button>
          ) : null}
        </div>

        {info ? <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{info}</div> : null}
        {error ? <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        {!context ? (
          <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <Card>
              <CardHeader>
                <CardTitle>{activeRoomName}</CardTitle>
                <CardDescription>
                  This invitation bootstraps a room-scoped external session. Your email must match the provisioned recipient.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="neutral">Room read</Badge>
                  {canDownload ? <Badge variant="neutral">Download</Badge> : null}
                  {inspection?.can_print ? <Badge variant="neutral">Print flag</Badge> : null}
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-zinc-900">Email confirmation</label>
                  <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
                </div>
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600">
                  The invitation itself is short-lived. After email confirmation, HexShare creates a room session backed by the provisioned external grant.
                </div>
                <div className="flex justify-end">
                  <Button onClick={() => void handleCreateSession()} disabled={isSubmitting || !email.trim()}>
                    {isSubmitting ? 'Starting session...' : 'Open room'}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Invitation details</CardTitle>
                <CardDescription>Sender-set recipient identity and invitation timing.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm text-zinc-600">
                <div>
                  <p className="font-medium text-zinc-900">Recipient</p>
                  <p>{inspection?.display_name || 'Unnamed recipient'}</p>
                  <p className="text-zinc-500">{inspection?.email}</p>
                </div>
                <div>
                  <p className="font-medium text-zinc-900">Invitation expires</p>
                  <p>{inspection?.expires_at ? format(new Date(inspection.expires_at), 'MMM d, yyyy h:mm a') : 'Unknown'}</p>
                </div>
                {inviteUrl ? (
                  <div className="space-y-2">
                    <p className="font-medium text-zinc-900">Invitation URL</p>
                    <p className="break-all rounded-lg bg-zinc-50 px-3 py-2 font-mono text-xs">{inviteUrl}</p>
                    <div className="flex gap-2">
                      <Button type="button" variant="outline" size="sm" onClick={() => void copyToClipboard(inviteUrl)}>
                        <Copy className="mr-2 h-4 w-4" />
                        {copiedValue === inviteUrl ? 'Copied' : 'Copy'}
                      </Button>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-start">
              <Card>
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <CardTitle>{context.room_name}</CardTitle>
                      <CardDescription>
                        Signed in as {context.display_name || context.email}. Access stays scoped to this room and recipient identity.
                      </CardDescription>
                    </div>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                      <FolderOpen className="h-6 w-6" />
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="success">Active room session</Badge>
                    <Badge variant="neutral">{documentCountLabel}</Badge>
                    {context.can_download ? <Badge variant="neutral">Download enabled</Badge> : null}
                  </div>
                  <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600">
                    Download actions are individually audited against this provisioned external identity.
                  </div>
                </CardContent>
              </Card>

              <Card className="lg:w-80">
                <CardHeader>
                  <CardTitle>Access subject</CardTitle>
                  <CardDescription>Provisioned external identity bound to this room session.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 text-sm text-zinc-600">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-100 text-zinc-700">
                      <Shield className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-medium text-zinc-900">{context.display_name || 'Unnamed recipient'}</p>
                      <p>{context.email}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="neutral">Room read</Badge>
                    {context.can_download ? <Badge variant="neutral">Download</Badge> : null}
                    {context.can_print ? <Badge variant="neutral">Print</Badge> : null}
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Room documents</CardTitle>
                <CardDescription>Only documents in the provisioned room are visible here.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {documents.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-zinc-200 px-6 py-10 text-center text-sm text-zinc-500">
                    No documents are currently visible in this room.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {documents.map((document) => (
                      <div key={document.id} className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-zinc-50/60 p-4 md:flex-row md:items-center md:justify-between">
                        <div className="space-y-1">
                          <p className="font-medium text-zinc-900">{document.name}</p>
                          <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
                            <span>{document.mime_type}</span>
                            <span>{formatBytes(document.size)}</span>
                            <span>Uploaded {format(new Date(document.created_at), 'MMM d, yyyy')}</span>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button type="button" size="sm" onClick={() => void handleOpenViewer(document.id)}>
                            <Eye className="mr-2 h-4 w-4" />
                            Open viewer
                          </Button>
                          {context.can_download ? (
                            <Button type="button" variant="outline" size="sm" onClick={() => void handleDownload(document.id)}>
                              <Download className="mr-2 h-4 w-4" />
                              Download
                            </Button>
                          ) : (
                            <Button type="button" variant="outline" size="sm" disabled>
                              <Mail className="mr-2 h-4 w-4" />
                              View only
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
