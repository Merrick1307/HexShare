import { FileText, ShieldCheck } from 'lucide-react';
import { useNdaAcceptance, type NdaGateProps } from '../hooks/useNdaAcceptance';
import { Button } from './ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/Card';
import { Input } from './ui/Input';

export type { NdaGateProps } from '../hooks/useNdaAcceptance';

type NdaGateComponentProps = NdaGateProps & {
  pdfUrl?: string | null;
};

export function NdaGate({ status, pdfUrl, onAccept }: NdaGateComponentProps) {
  const {
    policy,
    isPdf,
    requireScroll,
    requireSignature,
    scrolledToEnd,
    typedName,
    setTypedName,
    agreed,
    setAgreed,
    submitting,
    error,
    scrollRef,
    canAccept,
    handleScroll,
    handleAccept,
  } = useNdaAcceptance({ status, onAccept });

  return (
    <Card className="mx-auto w-full max-w-3xl border-zinc-200">
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <CardTitle className="text-xl">{policy?.title || 'Non-Disclosure Agreement'}</CardTitle>
            <CardDescription>
              {policy?.scope_type === 'document'
                ? 'You must accept this agreement before this document can be opened.'
                : 'You must accept this agreement before any document in this room can be opened.'}
              {policy ? ` (v${policy.version})` : ''}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isPdf ? (
          <div className="overflow-hidden rounded-lg border border-zinc-200">
            {pdfUrl ? (
              <iframe title="NDA document" src={pdfUrl} className="h-[420px] w-full" />
            ) : (
              <div className="flex h-[200px] items-center justify-center gap-2 text-sm text-zinc-500">
                <FileText className="h-4 w-4" /> NDA document
              </div>
            )}
          </div>
        ) : (
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="h-[360px] overflow-y-auto whitespace-pre-wrap rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm leading-relaxed text-zinc-800"
          >
            {status.text_body || 'No NDA content available.'}
          </div>
        )}

        {requireScroll && !scrolledToEnd ? (
          <p className="text-xs text-amber-600">Scroll to the end of the agreement to continue.</p>
        ) : null}

        {requireSignature ? (
          <div className="space-y-1">
            <label className="text-sm font-medium text-zinc-900">Type your full name to sign</label>
            <Input
              value={typedName}
              onChange={(event) => setTypedName(event.target.value)}
              placeholder="Your full name"
            />
          </div>
        ) : null}

        <label className="flex items-start gap-3 text-sm text-zinc-700">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4"
            checked={agreed}
            onChange={(event) => setAgreed(event.target.checked)}
          />
          <span>I have read and agree to the terms of this Non-Disclosure Agreement.</span>
        </label>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        <div className="flex justify-end">
          <Button onClick={() => void handleAccept()} disabled={!canAccept || submitting}>
            {submitting ? 'Recording…' : 'Accept & continue'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
