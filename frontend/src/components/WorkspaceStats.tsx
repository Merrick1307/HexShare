import { useEffect, useState } from 'react';
import { FileText, FolderOpen, Link2, Users, Eye } from 'lucide-react';
import { api } from '../services/api';
import { WorkspaceSummary } from '../types';

const CARDS: { key: keyof WorkspaceSummary; label: string; icon: typeof FileText }[] = [
  { key: 'documents', label: 'Documents', icon: FileText },
  { key: 'groups', label: 'Rooms', icon: FolderOpen },
  { key: 'active_links', label: 'Active links', icon: Link2 },
  { key: 'external_recipients', label: 'External recipients', icon: Users },
  { key: 'document_opens', label: 'Document opens', icon: Eye },
];

export function WorkspaceStats({ documentsLabel = 'Documents' }: { documentsLabel?: string }) {
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getWorkspaceSummary()
      .then((s) => !cancelled && setSummary(s))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {CARDS.map(({ key, label, icon: Icon }) => (
        <div key={key} className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-2 text-zinc-500">
            <Icon className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wide">
              {key === 'documents' ? documentsLabel : label}
            </span>
          </div>
          <p className="mt-2 text-2xl font-semibold text-zinc-950">
            {summary ? summary[key] : '—'}
          </p>
        </div>
      ))}
    </div>
  );
}
