import { useEffect, useRef, useState } from 'react';
import { FileText, ShieldCheck, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import { NdaAcceptanceRecord, NdaPolicyAdminView } from '../types';
import { Button } from './ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/Card';
import { Input } from './ui/Input';

interface NdaAdminPanelProps {
  scope: 'room' | 'document';
  id: string;
}

export function NdaAdminPanel({ scope, id }: NdaAdminPanelProps) {
  const [policy, setPolicy] = useState<NdaPolicyAdminView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [mode, setMode] = useState<'text' | 'pdf'>('text');
  const [title, setTitle] = useState('');
  const [textBody, setTextBody] = useState('');
  const [requireScroll, setRequireScroll] = useState(true);
  const [requireSignature, setRequireSignature] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [acceptances, setAcceptances] = useState<NdaAcceptanceRecord[] | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const get = scope === 'room' ? api.getGroupNda : api.getDocumentNda;
  const setText = scope === 'room' ? api.setGroupNdaText : api.setDocumentNdaText;
  const setPdf = scope === 'room' ? api.setGroupNdaPdf : api.setDocumentNdaPdf;
  const remove = scope === 'room' ? api.deleteGroupNda : api.deleteDocumentNda;
  const listAcceptances = scope === 'room' ? api.listGroupNdaAcceptances : api.listDocumentNdaAcceptances;

  useEffect(() => {
    let cancelled = false;
    get(id)
      .then((p) => {
        if (cancelled) return;
        setPolicy(p);
        if (p) {
          setTitle(p.title || '');
          setRequireScroll(p.require_scroll);
          setRequireSignature(p.require_typed_signature);
          setMode(p.content_type === 'pdf' ? 'pdf' : 'text');
        }
      })
      .catch(() => setPolicy(null))
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, id]);

  async function handleSave() {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      let saved: NdaPolicyAdminView;
      if (mode === 'text') {
        saved = await setText(id, {
          title: title || undefined,
          text_body: textBody,
          require_scroll: requireScroll,
          require_typed_signature: requireSignature,
        });
      } else {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error('Choose a PDF file to upload.');
        saved = await setPdf(id, file, {
          title: title || undefined,
          require_scroll: requireScroll,
          require_typed_signature: requireSignature,
        });
      }
      setPolicy(saved);
      setTextBody('');
      if (fileRef.current) fileRef.current.value = '';
      setInfo(`NDA saved (v${saved.version}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save NDA.');
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove() {
    setBusy(true);
    setError(null);
    try {
      await remove(id);
      setPolicy(null);
      setAcceptances(null);
      setInfo('NDA removed. This scope is no longer gated.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove NDA.');
    } finally {
      setBusy(false);
    }
  }

  async function handleShowAcceptances() {
    try {
      setAcceptances(await listAcceptances(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load acceptances.');
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-indigo-600" />
          <CardTitle>NDA gate</CardTitle>
        </div>
        <CardDescription>
          Require recipients to accept a Non-Disclosure Agreement before opening
          {scope === 'room' ? ' any document in this room.' : ' this document.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!loaded ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : (
          <>
            {policy ? (
              <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
                <span className="text-emerald-800">
                  Active NDA · {policy.content_type.toUpperCase()} · v{policy.version}
                  {policy.title ? ` · ${policy.title}` : ''}
                </span>
                <Button variant="outline" size="sm" onClick={() => void handleRemove()} disabled={busy}>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Remove
                </Button>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-zinc-200 px-4 py-3 text-sm text-zinc-500">
                No NDA set — this scope is not gated.
              </div>
            )}

            <div className="flex gap-2">
              <Button variant={mode === 'text' ? 'primary' : 'outline'} size="sm" onClick={() => setMode('text')}>
                Freeform text
              </Button>
              <Button variant={mode === 'pdf' ? 'primary' : 'outline'} size="sm" onClick={() => setMode('pdf')}>
                <FileText className="mr-2 h-4 w-4" />
                Upload PDF
              </Button>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-zinc-900">Title (optional)</label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Mutual NDA" />
            </div>

            {mode === 'text' ? (
              <div className="space-y-1">
                <label className="text-sm font-medium text-zinc-900">NDA text</label>
                <textarea
                  value={textBody}
                  onChange={(e) => setTextBody(e.target.value)}
                  rows={8}
                  className="w-full rounded-lg border border-zinc-200 p-3 text-sm"
                  placeholder="Paste the full agreement text…"
                />
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-sm font-medium text-zinc-900">NDA PDF</label>
                <input ref={fileRef} type="file" accept="application/pdf" className="block w-full text-sm" />
              </div>
            )}

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-zinc-700">
                <input type="checkbox" checked={requireScroll} onChange={(e) => setRequireScroll(e.target.checked)} />
                Require scroll-to-end
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-700">
                <input type="checkbox" checked={requireSignature} onChange={(e) => setRequireSignature(e.target.checked)} />
                Require typed signature
              </label>
            </div>

            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {info ? <p className="text-sm text-emerald-700">{info}</p> : null}

            <div className="flex items-center justify-between">
              <Button onClick={() => void handleSave()} disabled={busy}>
                {busy ? 'Saving…' : policy ? 'Update NDA' : 'Set NDA'}
              </Button>
              {policy ? (
                <Button variant="ghost" size="sm" onClick={() => void handleShowAcceptances()}>
                  View acceptances
                </Button>
              ) : null}
            </div>

            {acceptances ? (
              <div className="rounded-lg border border-zinc-200">
                <div className="border-b border-zinc-100 px-4 py-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Acceptances ({acceptances.length})
                </div>
                {acceptances.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-zinc-500">No acceptances recorded yet.</p>
                ) : (
                  <ul className="divide-y divide-zinc-100">
                    {acceptances.map((a) => (
                      <li key={a.id} className="flex items-center justify-between px-4 py-2 text-sm">
                        <span className="text-zinc-800">
                          {a.typed_name || a.subject_id} {a.presented_email ? `· ${a.presented_email}` : ''}
                        </span>
                        <span className="text-xs text-zinc-500">
                          v{a.nda_version} · {new Date(a.accepted_at).toLocaleString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
