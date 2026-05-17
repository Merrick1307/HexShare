import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import DOMPurify from 'dompurify';
import { Download, FileText, Lock, Printer } from 'lucide-react';
import { api } from '../services/api';
import { ShareInspection, ViewSession } from '../types';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';

type ViewerStatus = 'active' | 'revoked' | 'expired' | 'closed' | 'not_found';

type PreviewState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'pdf_pages'; pageCount: number; pathTemplate: string }
  | { kind: 'image'; src: string; alt: string }
  | { kind: 'html'; html: string }
  | { kind: 'unsupported'; message: string };

function getInlineUnsupportedMessage(session: ViewSession) {
  if (session.view_kind === 'docx') {
    return 'This Word document is not available for inline viewing yet. Download remains available only when the share link explicitly allows it.';
  }
  if (session.view_reason === 'inline_view_not_supported') {
    return 'This file type is not available for inline viewing in the secure viewer. Download remains available only when the share link explicitly allows it.';
  }
  if (session.view_reason === 'inline_view_backend_unavailable') {
    return 'The secure viewer backend for this document type is currently unavailable.';
  }
  return 'Preview is not available for this file type in the secure viewer.';
}

function buildPdfRenderWidth() {
  const viewportWidth = Math.max(window.innerWidth - 96, 400);
  const scaled = Math.round(viewportWidth * Math.max(window.devicePixelRatio || 1, 1));
  return Math.max(400, Math.min(scaled, 2200));
}

function buildPdfPageUrl(pathTemplate: string, pageNumber: number, renderWidth: number) {
  const pagePath = pathTemplate.replace('{page}', String(pageNumber));
  const absolute = api.toAbsoluteApiUrl(pagePath);
  return `${absolute}?width=${renderWidth}`;
}

function preloadPdfPageImage(pathTemplate: string, pageNumber: number, renderWidth: number) {
  const image = new Image();
  image.src = buildPdfPageUrl(pathTemplate, pageNumber, renderWidth);
  return image;
}

function buildViewerContentUrl(path: string) {
  return api.toAbsoluteApiUrl(path);
}

function PdfPagePlaceholder() {
  return <div className="h-full w-full animate-pulse rounded-sm bg-zinc-100" />;
}

interface LazyPdfPageProps {
  pageNumber: number;
  pathTemplate: string;
  pdfRenderWidth: number;
  documentName: string;
  onRef: (el: HTMLDivElement | null, pageNumber: number) => void;
}

function LazyPdfPage({ pageNumber, pathTemplate, pdfRenderWidth, documentName, onRef }: LazyPdfPageProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isVisible, setIsVisible] = useState(pageNumber === 1);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || isVisible) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '300px 0px' }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [isVisible]);

  return (
    <div
      ref={(element) => {
        containerRef.current = element;
        onRef(element, pageNumber);
      }}
      data-page-number={pageNumber}
      className="mx-auto flex w-full max-w-5xl flex-col gap-2"
    >
      <div className="text-center text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">Page {pageNumber}</div>
      <div className="relative w-full overflow-hidden rounded-sm bg-white shadow-2xl [aspect-ratio:8.5/11]">
        {isVisible ? (
          <img
            src={buildPdfPageUrl(pathTemplate, pageNumber, pdfRenderWidth)}
            alt={`${documentName} page ${pageNumber}`}
            className="absolute inset-0 h-full w-full object-contain"
          />
        ) : (
          <PdfPagePlaceholder />
        )}
      </div>
    </div>
  );
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
  const [activePage, setActivePage] = useState(1);
  const [pdfRenderWidth, setPdfRenderWidth] = useState(() => buildPdfRenderWidth());
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const isOpeningSessionRef = useRef(false);
  const prefetchedPagesRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (token) void inspectToken(token);
  }, [token]);

  useEffect(() => {
    const onResize = () => setPdfRenderWidth(buildPdfRenderWidth());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (!token || !inspection || inspection.require_email || inspection.revoked || inspection.expired || session || isOpeningSessionRef.current) return;
    isOpeningSessionRef.current = true;
    void openSession().finally(() => {
      isOpeningSessionRef.current = false;
    });
  }, [token, inspection, session]);

  useEffect(() => {
    if (!session) return;

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
      window.removeEventListener('beforeunload', closeSession);
      source.close();
    };
  }, [session]);

  useEffect(() => {
    if (!session || viewerStatus !== 'active') return;

    const timeout = window.setTimeout(() => {
      void api.sendPageView(session.session_id, activePage);
    }, 1500);

    return () => window.clearTimeout(timeout);
  }, [activePage, session, viewerStatus]);

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
    pageRefs.current = {};
    prefetchedPagesRef.current.clear();
    setActivePage(1);

    if (!session || viewerStatus !== 'active') {
      setPreview({ kind: 'idle' });
      return;
    }

    if (!session.inline_view_supported) {
      setPreview({
        kind: 'unsupported',
        message: getInlineUnsupportedMessage(session),
      });
      return;
    }

    let cancelled = false;

    const loadPreview = async () => {
      setPreview({ kind: 'loading' });

      if (session.view_kind === 'pdf') {
        if (session.page_image_path_template && session.page_count && session.page_count > 0) {
          if (!cancelled) {
            setPreview({
              kind: 'pdf_pages',
              pageCount: session.page_count,
              pathTemplate: session.page_image_path_template,
            });
          }
          return;
        }

        if (!cancelled) {
          setPreview({
            kind: 'unsupported',
            message: 'The PDF preview metadata is incomplete.',
          });
        }
        return;
      }

      try {
        if (session.view_kind === 'image') {
          setPreview({
            kind: 'image',
            src: buildViewerContentUrl(session.content_path),
            alt: session.document_name,
          });
          return;
        }

        const response = await api.fetchViewerContent(session.content_path);
        if (cancelled) return;
        const contentType = (response.headers.get('content-type') || '').toLowerCase();

        if (session.view_kind === 'text' || session.view_kind === 'markdown' || session.view_kind === 'code' || contentType.includes('text/html')) {
          const html = await response.text();
          if (cancelled) return;
          setPreview({ kind: 'html', html: DOMPurify.sanitize(html) });
          return;
        }

        setPreview({
          kind: 'unsupported',
          message: getInlineUnsupportedMessage(session),
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
    };
  }, [session, viewerStatus]);

  useEffect(() => {
    if (preview.kind !== 'pdf_pages') return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visiblePages = entries
          .filter((entry) => entry.isIntersecting)
          .map((entry) => Number((entry.target as HTMLElement).dataset.pageNumber || '1'))
          .filter((pageNumber) => Number.isFinite(pageNumber))
          .sort((left, right) => left - right);
        if (visiblePages.length > 0) {
          setActivePage(visiblePages[0]);
        }
      },
      {
        threshold: 0.6,
      }
    );

    (Object.values(pageRefs.current) as Array<HTMLDivElement | null>).forEach((element) => {
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, [preview, pdfRenderWidth]);

  useEffect(() => {
    if (preview.kind !== 'pdf_pages' || viewerStatus !== 'active') return;

    const nextPage = activePage + 1;
    if (nextPage > preview.pageCount) return;

    const prefetchKey = `${preview.pathTemplate}:${pdfRenderWidth}:${nextPage}`;
    if (prefetchedPagesRef.current.has(prefetchKey)) return;

    prefetchedPagesRef.current.add(prefetchKey);
    preloadPdfPageImage(preview.pathTemplate, nextPage, pdfRenderWidth);
  }, [activePage, pdfRenderWidth, preview, viewerStatus]);

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

  const handlePrint = () => {
    if (inspection?.permissions?.print) {
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
      return <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">Loading protected preview...</div>;
    }

    if (preview.kind === 'pdf_pages') {
      const pages = Array.from({ length: preview.pageCount }, (_, index) => index + 1);
      return (
        <div className="h-full w-full overflow-auto bg-zinc-200">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-3 py-4 md:px-6 md:py-6">
            {pages.map((pageNumber) => (
              <React.Fragment key={pageNumber}>
                <LazyPdfPage
                  pageNumber={pageNumber}
                  pathTemplate={preview.pathTemplate}
                  pdfRenderWidth={pdfRenderWidth}
                  documentName={session.document_name}
                  onRef={(element, observedPageNumber) => {
                    pageRefs.current[observedPageNumber] = element;
                  }}
                />
              </React.Fragment>
            ))}
          </div>
        </div>
      );
    }

    if (preview.kind === 'image') {
      return (
        <div className="flex h-full w-full items-center justify-center overflow-auto bg-zinc-200 p-4 md:p-8">
          <img
            src={preview.src}
            alt={preview.alt}
            className="max-h-full max-w-full rounded-sm bg-white shadow-2xl"
          />
        </div>
      );
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
        <div className="relative z-10 flex h-full w-full min-h-0 flex-col bg-white">
          <div className="relative flex min-h-0 flex-1 bg-zinc-100">
            {renderPreview()}
          </div>
        </div>
      </main>
    </div>
  );
}
