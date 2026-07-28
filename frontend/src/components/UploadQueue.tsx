import { useMemo, useRef, useState } from 'react';
import { CheckCircle2, RefreshCw, Trash2, XCircle } from 'lucide-react';
import { api } from '../services/api';
import type { Document } from '../types';
import {
  ACCEPTED_DOCUMENTS_ATTRIBUTE,
  BULK_UPLOAD_CONCURRENCY,
  estimateProtection,
  isAcceptedDocument,
  MAX_BULK_UPLOAD_FILES,
  SUPPORTED_DOCUMENT_MESSAGE,
} from '../lib/supportedDocuments';
import { formatBytes } from '../lib/utils';
import { Badge } from './ui/Badge';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { FileTypeIcon } from './FileTypeIcon';
import { Modal } from './ui/Modal';

type UploadStatus = 'queued' | 'initiating' | 'uploading' | 'finalizing' | 'complete' | 'failed';
type QueueItem = {
  id: string;
  file: File;
  status: UploadStatus;
  error?: string;
  document?: Document;
};

export function UploadQueue({
  roomId,
  sectionId,
  onSettled,
  onClose,
}: {
  roomId?: string | null;
  sectionId?: string | null;
  onSettled: (result: { successful: number; failed: number }) => void | Promise<void>;
  onClose: () => void;
}) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [completionNotice, setCompletionNotice] = useState<number | null>(null);
  const runId = useRef(0);

  const successful = items.filter((item) => item.status === 'complete').length;
  const failed = items.filter((item) => item.status === 'failed').length;
  const queued = items.filter((item) => item.status === 'queued').length;
  const totalBytes = useMemo(() => items.reduce((sum, item) => sum + item.file.size, 0), [items]);

  function addFiles(files: File[]) {
    setSelectionError(null);
    const unique = files.filter(
      (file, index) => files.findIndex((candidate) =>
        candidate.name === file.name && candidate.size === file.size && candidate.lastModified === file.lastModified
      ) === index
    );
    const rejected = unique.filter((file) => !isAcceptedDocument(file));
    if (rejected.length) {
      setSelectionError('Choose a supported business document: PDF, Office, text, CSV, Markdown, PNG, JPEG, or WebP.');
      return;
    }
    if (items.length + unique.length > MAX_BULK_UPLOAD_FILES) {
      setSelectionError(`Select no more than ${MAX_BULK_UPLOAD_FILES} documents at once.`);
      return;
    }
    setItems((current) => [
      ...current,
      ...unique.map((file, index) => ({
        id: `${Date.now()}-${index}-${file.name}`,
        file,
        status: 'queued' as const,
      })),
    ]);
  }

  function updateItem(id: string, update: Partial<QueueItem>) {
    setItems((current) => current.map((item) => item.id === id ? { ...item, ...update } : item));
  }

  async function uploadOne(item: QueueItem) {
    try {
      updateItem(item.id, { status: 'initiating', error: undefined });
      const initiated = await api.initiateUpload(item.file);
      updateItem(item.id, { status: 'uploading' });
      await api.uploadFileDirect(item.file, initiated);
      updateItem(item.id, { status: 'finalizing' });
      const document = await api.completeUpload({
        document_id: initiated.document_id,
        object_key: initiated.object_key,
        name: item.file.name,
        mime_type: item.file.type || 'application/octet-stream',
        size: item.file.size,
        room_id: roomId || undefined,
        room_section_id: sectionId || undefined,
      });
      updateItem(item.id, { status: 'complete', document });
      return true;
    } catch (error) {
      updateItem(item.id, {
        status: 'failed',
        error: error instanceof Error ? error.message : 'Upload failed',
      });
      return false;
    }
  }

  async function runQueue(onlyIds?: Set<string>) {
    if (isRunning) return;
    const candidates = items.filter((item) =>
      onlyIds ? onlyIds.has(item.id) : item.status === 'queued'
    );
    if (!candidates.length) return;
    setIsRunning(true);
    const currentRun = ++runId.current;
    let cursor = 0;
    let runSuccessful = 0;
    let runFailed = 0;
    const worker = async () => {
      while (cursor < candidates.length && currentRun === runId.current) {
        const item = candidates[cursor++];
        if (await uploadOne(item)) runSuccessful += 1;
        else runFailed += 1;
      }
    };
    await Promise.all(
      Array.from(
        { length: Math.min(BULK_UPLOAD_CONCURRENCY, candidates.length) },
        () => worker(),
      ),
    );
    setIsRunning(false);
    await onSettled({ successful: runSuccessful, failed: runFailed });
    const candidateIds = new Set(candidates.map((item) => item.id));
    const everyFileSucceeded = runFailed === 0 && items.every(
      (item) => candidateIds.has(item.id) || item.status === 'complete',
    );
    if (runSuccessful > 0 && everyFileSucceeded) {
      setCompletionNotice(runSuccessful);
    }
  }

  function retryFailed() {
    const failedIds = new Set(items.filter((item) => item.status === 'failed').map((item) => item.id));
    setItems((current) => current.map((item) =>
      failedIds.has(item.id) ? { ...item, status: 'queued', error: undefined } : item
    ));
    window.setTimeout(() => void runQueue(failedIds), 0);
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 dark:border-[#6657ff]/30 dark:bg-[#6657ff]/10">
        <p className="text-sm font-medium text-indigo-950 dark:text-[#f3f1eb]">Upload common business documents</p>
        <p className="mt-1 text-xs leading-5 text-indigo-800 dark:text-[#c8c3ff]">{SUPPORTED_DOCUMENT_MESSAGE}</p>
        <p className="mt-1 text-xs text-indigo-700 dark:text-[#a8a2ff]">Accepted: PDF, Word, Excel, PowerPoint, TXT, CSV, Markdown, PNG, JPEG, and WebP.</p>
      </div>
      {selectionError ? <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{selectionError}</div> : null}
      <Input
        type="file"
        multiple
        accept={ACCEPTED_DOCUMENTS_ATTRIBUTE}
        disabled={isRunning || items.length >= MAX_BULK_UPLOAD_FILES}
        onChange={(event) => {
          addFiles(Array.from(event.target.files || []));
          event.target.value = '';
        }}
      />
      {items.length ? (
        <div className="max-h-[min(18rem,35vh)] divide-y divide-zinc-100 overflow-y-auto overscroll-contain rounded-lg border border-zinc-200">
          {items.map((item) => {
            const protection = item.document?.protection || estimateProtection(item.file);
            return (
              <div key={item.id} className="flex items-start gap-3 px-3 py-3">
                <FileTypeIcon fileName={item.file.name} mimeType={item.file.type} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-zinc-900">{item.file.name}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span>{formatBytes(item.file.size)}</span>
                    <Badge variant={protection.profile === 'strongest' ? 'success' : 'neutral'}>{protection.label}</Badge>
                    <span className="capitalize">{item.status.replace('_', ' ')}</span>
                  </div>
                  {item.error ? <p className="mt-1 text-xs text-red-600">{item.error}</p> : null}
                </div>
                {item.status === 'complete' ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : null}
                {item.status === 'failed' ? <XCircle className="h-4 w-4 text-red-500" /> : null}
                {item.status === 'queued' ? (
                  <button type="button" title="Remove queued file" onClick={() => setItems((current) => current.filter((candidate) => candidate.id !== item.id))}>
                    <Trash2 className="h-4 w-4 text-zinc-400 hover:text-red-600" />
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
      {items.length ? (
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-500">
          <span>{items.length} file{items.length === 1 ? '' : 's'} · {formatBytes(totalBytes)} · {successful} complete · {failed} failed</span>
          <div className="flex gap-2">
            {failed > 0 && !isRunning ? (
              <Button type="button" variant="outline" size="sm" onClick={retryFailed}>
                <RefreshCw className="mr-2 h-4 w-4" /> Retry failed
              </Button>
            ) : null}
            <Button type="button" size="sm" disabled={isRunning || queued === 0} onClick={() => void runQueue()}>
              {isRunning ? 'Uploading…' : `Upload ${queued || ''}`.trim()}
            </Button>
          </div>
        </div>
      ) : null}
      <Modal
        isOpen={completionNotice !== null}
        onClose={() => setCompletionNotice(null)}
        title="Upload complete"
      >
        <div className="space-y-5">
          <div className="flex gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div>
              <p className="font-medium text-zinc-900">
                {completionNotice} document{completionNotice === 1 ? '' : 's'} uploaded successfully.
              </p>
              <p className="mt-1 text-sm text-zinc-500">
                You can close the upload window or keep it open to add more documents.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setCompletionNotice(null)}>
              Continue uploading
            </Button>
            <Button
              type="button"
              onClick={() => {
                setCompletionNotice(null);
                onClose();
              }}
            >
              OK
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
