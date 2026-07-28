import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { NotificationPreferences } from '../types';

export function NotificationPreferencesCard() {
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api.getNotificationPreferences().then(setPreferences).catch(() => undefined);
  }, []);

  if (!preferences) return null;

  async function update(key: keyof NotificationPreferences, value: boolean) {
    const next = { ...preferences!, [key]: value };
    setPreferences(next);
    setStatus('Saving…');
    try {
      setPreferences(await api.updateNotificationPreferences(next));
      setStatus('Saved');
    } catch (error) {
      setPreferences(preferences);
      setStatus(error instanceof Error ? error.message : 'Could not save');
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-zinc-950">Activity email notifications</h2>
          <p className="mt-1 text-sm text-zinc-500">Choose which meaningful recipient actions send you an email. Page views and heartbeats never send individual emails.</p>
        </div>
        {status ? <span className="text-xs text-zinc-400">{status}</span> : null}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {([
          ['document_open_email', 'First document open', 'Once per recipient session and document'],
          ['document_download_email', 'Document download', 'When a permitted download succeeds'],
          ['nda_accepted_email', 'NDA acceptance', 'Off by default'],
        ] as const).map(([key, label, description]) => (
          <label key={key} className="flex items-start gap-3 rounded-lg border border-zinc-100 bg-zinc-50 p-3">
            <input type="checkbox" className="mt-1" checked={preferences[key]} onChange={(event) => void update(key, event.target.checked)} />
            <span>
              <span className="block text-sm font-medium text-zinc-900">{label}</span>
              <span className="block text-xs text-zinc-500">{description}</span>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}
