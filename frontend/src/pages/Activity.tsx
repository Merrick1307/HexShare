import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import { Link } from 'react-router-dom';
import { Activity as ActivityIcon, Download, Eye, FileText, FolderOpen, LogIn, ShieldCheck } from 'lucide-react';
import { api } from '../services/api';
import { ActivityItem } from '../types';
import { Badge } from '../components/ui/Badge';
import { NotificationPreferencesCard } from '../components/NotificationPreferencesCard';

const EVENT_META: Record<string, { label: string; icon: typeof Eye }> = {
  open: { label: 'Opened document', icon: FileText },
  page_view: { label: 'Viewed page', icon: Eye },
  download_attempt: { label: 'Downloaded', icon: Download },
  blocked: { label: 'Blocked action', icon: ShieldCheck },
  close: { label: 'Closed viewer', icon: FileText },
  room_open: { label: 'Opened room', icon: FolderOpen },
  document_list: { label: 'Listed room documents', icon: FolderOpen },
  document_view_open: { label: 'Opened document', icon: FileText },
  document_page_view: { label: 'Viewed page', icon: Eye },
  document_view_close: { label: 'Closed document', icon: FileText },
  document_download: { label: 'Downloaded', icon: Download },
  nda_accepted: { label: 'Accepted NDA', icon: ShieldCheck },
  room_close: { label: 'Left room', icon: LogIn },
};

export function Activity() {
  const [items, setItems] = useState<ActivityItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getActivity(100)
      .then((data) => !cancelled && setItems(data))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Failed to load activity'));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">Activity</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every document open, page view, download, and NDA acceptance across your workspace — with per-recipient attribution.
        </p>
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

      <NotificationPreferencesCard />

      <div className="overflow-y-auto rounded-xl border border-zinc-200 bg-white shadow-sm max-h-[calc(100vh-16rem)]">
        {items === null ? (
          <div className="px-6 py-10 text-center text-sm text-zinc-500">Loading activity…</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-14 text-center text-sm text-zinc-500">
            <ActivityIcon className="mb-3 h-8 w-8 text-zinc-300" />
            <p className="font-medium text-zinc-900">No recipient activity yet</p>
            <p className="mt-1">Share a document or invite someone to a room; verified views, downloads, and NDA acceptances will appear here.</p>
            <div className="mt-4 flex gap-3">
              <Link to="/dashboard" className="rounded-lg bg-indigo-600 px-3 py-2 font-medium text-white hover:bg-indigo-700">Share a document</Link>
              <Link to="/groups" className="rounded-lg border border-zinc-300 px-3 py-2 font-medium text-zinc-700 hover:bg-zinc-50">Open rooms</Link>
            </div>
          </div>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {items.map((item, index) => {
              const meta = EVENT_META[item.event_type] || { label: item.event_type, icon: ActivityIcon };
              const Icon = meta.icon;
              const target = item.document_name || item.room_name || '—';
              return (
                <li key={index} className="flex items-center gap-4 px-6 py-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-zinc-900">
                      <span className="font-medium">{meta.label}</span>
                      {item.page_number ? <span className="text-zinc-500"> · page {item.page_number}</span> : null}
                      <span className="text-zinc-500"> · {target}</span>
                    </p>
                    <p className="truncate text-xs text-zinc-500">
                      {item.actor || (item.source === 'room' ? 'External recipient' : 'Share-link visitor')}
                      {item.room_name ? ` · ${item.room_name}` : ''}
                    </p>
                  </div>
                  <Badge variant="neutral">{item.source === 'room' ? 'Room' : 'Link'}</Badge>
                  <span className="w-40 shrink-0 text-right text-xs text-zinc-400">
                    {format(new Date(item.timestamp), 'MMM d, yyyy h:mm a')}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
