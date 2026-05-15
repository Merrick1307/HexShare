import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { Download, FileText, Lock, Printer } from 'lucide-react';
import { api } from '../services/api';
import { ShareInspection, ViewSession } from '../types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';

type ViewerStatus = 'active' | 'revoked' | 'expired' | 'closed' | 'not_found';

type PreviewState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'pdf' | 'image'; src: string }
  | { kind: 'html'; html: string }
  | { kind: 'text'; text: string }
  | { kind: 'unsupported'; message: string };

function getFileExtension(name: string) {
  const parts = name.toLowerCase().split('.');
  return parts.length > 1 ? parts.pop() || '' : '';
}

function getPreviewKind(mimeType: string, fileName: string) {
  const normalizedMime = (mimeType || '').toLowerCase();
  const extension = getFileExtension(fileName);

  if (normalizedMime === 'application/pdf' || extension === 'pdf') return 'pdf';
  if (normalizedMime.startsWith('image/')) return 'image';
  if (normalizedMime.includes('markdown') || extension === 'md' || extension === 'markdown') return 'markdown';
  if (
    normalizedMime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    extension === 'docx'
  ) {
    return 'docx';
  }
  if (
    normalizedMime.startsWith('text/') ||
    normalizedMime === 'application/json' ||
    normalizedMime === 'application/xml' ||
    normalizedMime === 'text/csv' ||
    ['txt', 'log', 'csv', 'json', 'xml', 'yaml', 'yml'].includes(extension)
  ) {
    return 'text';
  }
  return 'unsupported';
}

export function ViewDocument() {
  const { token } = useParams<{ token: string }>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inspection, setInspection] = useState<ShareInspection | null>(null);
  const [email, setEmail] = useState('');
  const [session, setSession] = useState<ViewSession | null>(null);
  const [viewerStatus, setViewerStatus] = useState<ViewerStatus>('active');
  const [preview, setPreview] = useState<PreviewState>({ kind: 'idle' });
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const isOpeningSessionRef = useRef(false);

  useEffect(() => {
    if (token) void inspectToken(token);
  }, [token]);

  useEffect(() => {
    if (!token || !inspection || inspection.require_email || inspection.revoked || inspection.expired || session || isOpeningSessionRef.current) return;
    isOpeningSessionRef.current = true;
    void openSession().finally(() => {
      isOpeningSessionRef.current = false;
    });
  }, [token, inspection, session]);

  useEffect(() => {
    if (!session) return;

    const interval = window.setInterval(() => {
      void api.sendViewerHeartbeat(session.session_id, { page_number: 1, duration_ms: 20000 });
    }, 20000);

    const closeSession = () => {
      void api.closeViewSession(session.session_id);
    };

    window.addEventListener('beforeunload', closeSession);

    const eventsUrl = api.toAbsoluteApiUrl(session.events_path);
    const source = new EventSource(eventsUrl);
    source.addEventListener('status', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { status: ViewerStatus };
        if (payload.status !== 'active') setViewerStatus(payload.status);
      } catch {
        // ignore malformed event payloads
      }
    });
    source.onerror = () => {
      source.close();
    };

    return () => {
      window.clearInterval(interval);
      window.removeEventListener('beforeunload', closeSession);
      source.close();
    };
  }, [session]);

  useEffect(() => {
    if (!inspection || inspection.permissions?.print) return;
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p') {
        event.preventDefault();
      }
    };
    const contextHandler = (event: MouseEvent) => event.preventDefault();
    window.addEventListener('keydown', handler);
    window.addEventListener('contextmenu', contextHandler);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('contextmenu', contextHandler);
    };
  }, [inspection]);

  useEffect(() => {
    if (!session || viewerStatus !== 'active') {
      setPreview({ kind: 'idle' });
      return;
    }

    let objectUrl: string | null = null;
    let cancelled = false;

    const loadPreview = async () => {
      setPreview({ kind: 'loading' });
      try {
        const response = await api.fetchViewerContent(session.content_path);
        if (cancelled) return;

        const previewKind = getPreviewKind(session.mime_type, session.document_name);

        if (previewKind === 'pdf' || previewKind === 'image') {
          const blob = await response.blob();
          if (cancelled) return;
          objectUrl = URL.createObjectURL(blob);
          setPreview({ kind: previewKind, src: previewKind === 'pdf' ? `${objectUrl}#toolbar=0&navpanes=0&scrollbar=0&view=FitH&zoom=page-fit` : objectUrl });
          return;
        }

        if (previewKind === 'markdown') {
          const text = await response.text();
          if (cancelled) return;
          const renderedHtml = marked.parse(text, { async: false, breaks: true }) as string;
          setPreview({ kind: 'html', html: DOMPurify.sanitize(renderedHtml) });
          return;
        }

        if (previewKind === 'text') {
          const text = await response.text();
          if (cancelled) return;
          setPreview({ kind: 'text', text });
          return;
        }

        if (previewKind === 'docx') {
          const arrayBuffer = await response.arrayBuffer();
          if (cancelled) return;
          try {
            const mammothModule = await import('mammoth');
            const mammoth = (mammothModule as unknown as { default?: typeof mammothModule }).default || mammothModule;
            const result = await mammoth.convertToHtml({ arrayBuffer });
            if (cancelled) return;
            setPreview({ kind: 'html', html: DOMPurify.sanitize(result.value) });
          } catch {
            setPreview({
              kind: 'unsupported',
              message: 'This Word document could not be rendered safely in the browser. The raw file is not being auto-downloaded because downloads are restricted.',
            });
          }
          return;
        }

        setPreview({
          kind: 'unsupported',
          message: 'Preview is not available for this file type in the browser viewer. Downloads remain restricted unless the share link explicitly allows them.',
        });
      } catch (err) {
        if (cancelled) return;
        setPreview({
          kind: 'unsupported',
          message: err instanceof Error ? err.message : 'Unable to load the protected document preview.',
        });
      }
    };

    void loadPreview();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [session, viewerStatus]);

  async function inspectToken(tokenId: string) {
    setIsLoading(true);
    setError(null);
    try {
      const nextInspection = await api.inspectShareLink(tokenId);
      setInspection(nextInspection);
      setViewerStatus(nextInspection.revoked ? 'revoked' : nextInspection.expired ? 'expired' : 'active');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to verify share token');
    } finally {
      setIsLoading(false);
    }
  }

  async function openSession(overrideEmail?: string) {
    if (!token) return;
    setError(null);
    try {
      const nextSession = await api.createViewSession(token, overrideEmail ?? email);
      setSession(nextSession);
      setViewerStatus('active');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open viewer session');
    }
  }

  function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    void openSession(email.trim());
  }

  const watermark = session?.watermark_text || `HexShare • ${inspection?.link || ''}`;
  const isProtectedFromPrint = !inspection?.permissions?.print;

  const handlePrint = () => {
    if (preview.kind === 'pdf') {
      iframeRef.current?.contentWindow?.print();
      return;
    }
    if (!isProtectedFromPrint) {
      window.print();
    }
  };

  if (isLoading) return <div className="flex min-h-screen items-center justify-center bg-zinc-50"><div className="flex animate-pulse flex-col items-center"><div className="mb-4 h-12 w-12 rounded-full bg-zinc-200" /><div className="h-4 w-32 rounded bg-zinc-200" /></div></div>;
  if (error) return <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4"><Card className="w-full max-w-md text-center"><CardHeader><div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600"><Lock className="h-6 w-6" /></div><CardTitle className="text-xl text-zinc-900">Access denied</CardTitle><CardDescription className="mt-2 text-zinc-500">{error}</CardDescription></CardHeader></Card></div>;
  if (!inspection) return null;

  if (viewerStatus !== 'active' && !session) {
    const label = viewerStatus === 'revoked' ? 'This share link has been revoked.' : viewerStatus === 'expired' ? 'This share link has expired.' : 'This share link is not available.';
    return <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4"><Card className="w-full max-w-md text-center"><CardHeader><div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600"><Lock className="h-6 w-6" /></div><CardTitle className="text-xl text-zinc-900">Viewer unavailable</CardTitle><CardDescription className="mt-2 text-zinc-500">{label}</CardDescription></CardHeader></Card></div>;
  }

  if (inspection.require_email && !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center"><div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-indigo-600"><Lock className="h-6 w-6" /></div><CardTitle className="text-xl text-zinc-900">Secure document</CardTitle><CardDescription className="mt-2 text-zinc-500">This share link requires email verification before the viewer can continue.</CardDescription></CardHeader>
          <CardContent><form onSubmit={handleEmailSubmit} className="space-y-4"><Input type="email" placeholder="Enter your email address" value={email} onChange={(e) => setEmail(e.target.value)} required className="w-full" /><Button type="submit" className="w-full">Verify access</Button></form></CardContent>
        </Card>
      </div>
    );
  }

  if (!session) return null;

  const renderPreview = () => {
    if (viewerStatus !== 'active') {
      return (
        <div className="flex flex-1 items-center justify-center p-10 text-center text-zinc-500">
          <div>
            <p className="text-lg font-semibold text-zinc-900">Viewer access ended</p>
            <p className="mt-2">This session is now {viewerStatus}. Refreshing or requesting more content will no longer work.</p>
          </div>
        </div>
      );
    }

    if (preview.kind === 'loading' || preview.kind === 'idle') {
      return <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">Loading protected preview…</div>;
    }

    if (preview.kind === 'image') {
      return (
        <div className="flex h-full w-full items-center justify-center overflow-auto p-4 md:p-6">
          <img src={preview.src} alt={session.document_name} className="max-h-full max-w-full object-contain shadow-xl" />
        </div>
      );
    }

    if (preview.kind === 'pdf') {
      return <iframe ref={iframeRef} src={preview.src} title={session.document_name} className="h-full w-full min-h-0 border-0 bg-white" />;
    }

    if (preview.kind === 'html') {
      return (
        <div className="h-full w-full overflow-auto bg-zinc-100 p-4 md:p-8">
          <article
            className="mx-auto w-full max-w-4xl rounded-2xl bg-white p-6 shadow-lg md:p-10 [&_a]:text-indigo-600 [&_blockquote]:border-l-4 [&_blockquote]:border-zinc-200 [&_blockquote]:pl-4 [&_code]:rounded [&_code]:bg-zinc-100 [&_code]:px-1 [&_code]:py-0.5 [&_h1]:mb-4 [&_h1]:text-3xl [&_h1]:font-semibold [&_h2]:mb-3 [&_h2]:mt-8 [&_h2]:text-2xl [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:mt-6 [&_h3]:text-xl [&_h3]:font-semibold [&_li]:ml-6 [&_li]:list-disc [&_ol]:space-y-2 [&_p]:my-4 [&_pre]:overflow-auto [&_pre]:rounded-xl [&_pre]:bg-zinc-950 [&_pre]:p-4 [&_pre]:text-sm [&_pre]:text-zinc-100 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-zinc-200 [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-zinc-200 [&_th]:bg-zinc-50 [&_th]:px-3 [&_th]:py-2 [&_ul]:space-y-2"
            dangerouslySetInnerHTML={{ __html: preview.html }}
          />
        </div>
      );
    }

    if (preview.kind === 'text') {
      return (
        <div className="h-full w-full overflow-auto bg-zinc-100 p-4 md:p-8">
          <pre className="mx-auto w-full max-w-5xl whitespace-pre-wrap break-words rounded-2xl bg-white p-6 text-sm leading-6 text-zinc-800 shadow-lg md:p-10">{preview.text}</pre>
        </div>
      );
    }

    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <Card className="w-full max-w-2xl border-zinc-200 bg-white/95">
          <CardHeader>
            <CardTitle className="text-xl text-zinc-900">Preview unavailable</CardTitle>
            <CardDescription className="mt-2 text-zinc-500">{preview.message}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-zinc-950">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-800 bg-zinc-900 px-4 md:px-6">
        <div className="flex min-w-0 items-center gap-3"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-zinc-800 text-zinc-400"><FileText className="h-4 w-4" /></div><div className="min-w-0"><h1 className="truncate text-sm font-medium text-zinc-200">{session.document_name}</h1><p className="truncate text-xs text-zinc-500">Secure viewer session {session.session_id}</p></div></div>
        <div className="flex items-center gap-2">
          {session.permissions?.print ? <Button variant="ghost" size="sm" className="text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100" onClick={handlePrint}><Printer className="mr-2 h-4 w-4" />Print</Button> : null}
          {session.permissions?.download && session.download_path ? <Button variant="ghost" size="sm" className="text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100" onClick={() => window.open(api.toAbsoluteApiUrl(session.download_path || ''), '_blank', 'noopener,noreferrer')}><Download className="mr-2 h-4 w-4" />Download</Button> : null}
        </div>
      </header>
      <main className="relative flex min-h-0 flex-1 overflow-hidden bg-zinc-950">
        <div className="absolute inset-0 bg-zinc-950" />
        <div className="relative z-10 flex h-full w-full min-h-0 flex-col bg-white">
          <div className="relative flex min-h-0 flex-1 bg-zinc-100">
            <div className="pointer-events-none absolute inset-0 z-10 select-none opacity-20">
              <div className="flex h-full w-full items-center justify-center px-6 text-center text-2xl font-semibold tracking-wide text-zinc-500 [transform:rotate(-24deg)] md:text-3xl">{watermark}</div>
            </div>
            {renderPreview()}
          </div>
        </div>
      </main>
    </div>
  );
}
