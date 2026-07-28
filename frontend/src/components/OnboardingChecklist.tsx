import { useEffect, useMemo, useState } from 'react';
import { Check, Circle, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import type { WorkspaceSummary } from '../types';
import { Button } from './ui/Button';

const DISMISSED_KEY = 'hexshare:onboarding:dismissed';
const EVENT_KEY_PREFIX = 'hexshare:product-event:';

function recordOnce(eventName: Parameters<typeof api.recordProductEvent>[0]) {
  const key = `${EVENT_KEY_PREFIX}${eventName}`;
  if (window.localStorage.getItem(key) === 'true') return;
  window.localStorage.setItem(key, 'true');
  void api.recordProductEvent(eventName).catch(() => {
    window.localStorage.removeItem(key);
  });
}

export function OnboardingChecklist({ onUpload }: { onUpload: () => void }) {
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [summaryLoaded, setSummaryLoaded] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => window.localStorage.getItem(DISMISSED_KEY) === 'true',
  );

  useEffect(() => {
    let cancelled = false;
    recordOnce('onboarding_shown');
    api.getWorkspaceSummary()
      .then((value) => {
        if (!cancelled) setSummary(value);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setSummaryLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const steps = useMemo(() => [
    { label: 'Upload your first document', complete: (summary?.documents || 0) > 0 },
    { label: 'Create a room', complete: (summary?.groups || 0) > 0 },
    {
      label: 'Share with a recipient',
      complete: (summary?.active_links || 0) > 0 || (summary?.external_recipients || 0) > 0,
    },
    { label: 'See a recipient open', complete: (summary?.document_opens || 0) > 0 },
  ], [summary]);

  const completedCount = steps.filter((step) => step.complete).length;
  const complete = summary?.onboarding_complete ?? completedCount === steps.length;

  useEffect(() => {
    if (!summary) return;
    if (summary.documents > 0) recordOnce('first_document_uploaded');
    if (summary.groups > 0) recordOnce('first_room_created');
    if (summary.active_links > 0 || summary.external_recipients > 0) recordOnce('first_share_created');
    if (summary.document_opens > 0) recordOnce('first_recipient_viewed');
    if (complete) {
      recordOnce('onboarding_completed');
    }
  }, [complete, summary]);

  if (!summaryLoaded || dismissed || complete) return null;

  function dismiss() {
    window.localStorage.setItem(DISMISSED_KEY, 'true');
    recordOnce('onboarding_dismissed');
    setDismissed(true);
  }

  function recordStep(step: 'upload_document' | 'create_room' | 'create_share' | 'view_activity') {
    void api.recordProductEvent('onboarding_step_clicked', step).catch(() => undefined);
  }

  return (
    <section className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-5 dark:border-[#6657ff]/30 dark:bg-[#6657ff]/10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-zinc-950">Get your secure workspace ready</h2>
          <p className="mt-1 text-sm text-zinc-600">{completedCount} of {steps.length} complete</p>
        </div>
        <button type="button" onClick={dismiss} aria-label="Dismiss onboarding" className="rounded-md p-1 text-zinc-500 hover:bg-white">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {steps.map((step) => (
          <div key={step.label} className="flex items-center gap-2 text-sm text-zinc-700">
            {step.complete
              ? <Check className="h-4 w-4 text-emerald-600" />
              : <Circle className="h-4 w-4 text-zinc-400" />}
            <span className={step.complete ? 'text-zinc-500 line-through' : ''}>{step.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => { recordStep('upload_document'); onUpload(); }}>Upload document</Button>
        <Link to="/groups" onClick={() => recordStep('create_room')}><Button type="button" size="sm" variant="outline">Create a room</Button></Link>
        <Link to="/dashboard" onClick={() => recordStep('create_share')}><Button type="button" size="sm" variant="outline">Create protected link</Button></Link>
        <Link to="/activity" onClick={() => recordStep('view_activity')}><Button type="button" size="sm" variant="outline">View activity</Button></Link>
      </div>
    </section>
  );
}
