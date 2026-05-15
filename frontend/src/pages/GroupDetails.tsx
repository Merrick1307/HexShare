import { useCallback, useEffect, useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { format } from 'date-fns';
import { ArrowLeft, FileText, Upload, Folder, UserPlus, Search, ChevronLeft, ChevronRight, FolderOutput } from 'lucide-react';
import { api } from '../services/api';
import { Document, DocumentGroup } from '../types';
import { formatBytes } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';

type WorkspaceUser = { id: string; user_id?: string; email?: string; name?: string; username?: string };

export function GroupDetails() {
  const { id } = useParams<{ id: string }>();
  const [group, setGroup] = useState<DocumentGroup | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMemberModalOpen, setIsMemberModalOpen] = useState(false);
  const [memberUserId, setMemberUserId] = useState('');
  const [memberRole, setMemberRole] = useState<'member' | 'owner'>('member');
  const [memberError, setMemberError] = useState<string | null>(null);
  const [workspaceUsers, setWorkspaceUsers] = useState<WorkspaceUser[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const [usersSearch, setUsersSearch] = useState('');
  const [usersLoading, setUsersLoading] = useState(false);
  const PAGE_SIZE = 10;

  const loadData = useCallback(async () => {
    if (!id) return;
    setIsLoading(true);
    setError(null);
    try {
      const [groupData, docs] = await Promise.all([
        api.getGroup(id),
        api.listGroupDocuments(id),
      ]);
      setGroup(groupData);
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load group');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (!successMessage) return;
    const timer = window.setTimeout(() => setSuccessMessage(null), 3500);
    return () => window.clearTimeout(timer);
  }, [successMessage]);

  const loadWorkspaceUsers = useCallback(async (page: number, search: string) => {
    setUsersLoading(true);
    try {
      const result = await api.listWorkspaceUsers(page, PAGE_SIZE, search || undefined);
      setWorkspaceUsers(result.users);
      setUsersTotal(result.total);
    } catch {
      setWorkspaceUsers([]);
      setUsersTotal(0);
    } finally {
      setUsersLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isMemberModalOpen) {
      void loadWorkspaceUsers(usersPage, usersSearch);
    }
  }, [isMemberModalOpen, usersPage, usersSearch, loadWorkspaceUsers]);

  const totalPages = Math.ceil(usersTotal / PAGE_SIZE);

  function openMemberModal() {
    setMemberUserId('');
    setMemberRole('member');
    setMemberError(null);
    setUsersPage(1);
    setUsersSearch('');
    setIsMemberModalOpen(true);
  }

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!id) return;
    setUploadError(null);
    setIsSubmitting(true);

    const formData = new FormData(e.currentTarget);
    const file = formData.get('file') as File | null;

    if (!file) {
      setUploadError('Select a file first.');
      setIsSubmitting(false);
      return;
    }

    try {
      const uploadInit = await api.initiateUpload(file);
      await api.uploadFileDirect(file, uploadInit);
      await api.createDocumentInGroup(id, {
        name: file.name,
        mime_type: file.type || 'application/octet-stream',
        size: file.size,
        storage_key: uploadInit.object_key,
      });
      setIsUploadModalOpen(false);
      e.currentTarget.reset();
      setSuccessMessage('Document uploaded successfully.');
      await loadData();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Failed to upload');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAddMember() {
    if (!id || !memberUserId.trim()) return;
    setMemberError(null);
    setIsSubmitting(true);
    try {
      await api.addGroupMember(id, memberUserId.trim(), memberRole);
      setIsMemberModalOpen(false);
      setMemberUserId('');
      setMemberRole('member');
      setSuccessMessage(`Member added successfully.`);
    } catch (err) {
      setMemberError(err instanceof Error ? err.message : 'Failed to add member');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRemoveFromGroup(doc: Document) {
    if (!confirm(`Remove "${doc.name}" from this group?`)) return;
    setIsSubmitting(true);
    try {
      await api.moveDocumentToGroup(doc.id, null);
      setSuccessMessage('Document removed from group.');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove document');
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return <div className="py-12 text-center text-zinc-500">Loading...</div>;
  }

  if (error || !group) {
    return (
      <div className="space-y-4">
        <Link to="/groups" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900">
          <ArrowLeft className="h-4 w-4" /> Back to Groups
        </Link>
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error || 'Group not found'}</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <Link to="/groups" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900">
          <ArrowLeft className="h-4 w-4" /> Back to Groups
        </Link>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
            <Folder className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">{group.name}</h1>
            {group.description && <p className="mt-1 text-sm text-zinc-500">{group.description}</p>}
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={openMemberModal} className="gap-2">
            <UserPlus className="h-4 w-4" />
            Add Member
          </Button>
          <Button onClick={() => setIsUploadModalOpen(true)} className="gap-2">
            <Upload className="h-4 w-4" />
            Upload to Group
          </Button>
        </div>
      </div>

      {successMessage && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{successMessage}</div>}

      <div className="overflow-visible rounded-xl border border-zinc-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="px-6 py-4">Name</th>
              <th className="px-6 py-4">Size</th>
              <th className="px-6 py-4">Uploaded</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-zinc-500">
                  <div className="flex flex-col items-center justify-center">
                    <FileText className="mb-3 h-10 w-10 text-zinc-300" />
                    <p className="text-base font-medium text-zinc-900">No documents in this group</p>
                    <p className="mt-1 text-sm">Upload a document to get started.</p>
                  </div>
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id} className="group transition-colors hover:bg-zinc-50/50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                        <FileText className="h-5 w-5" />
                      </div>
                      <div>
                        <Link to={`/documents/${doc.id}`} className="font-medium text-zinc-900 hover:text-indigo-600 hover:underline">
                          {doc.name}
                        </Link>
                        <p className="mt-0.5 text-xs text-zinc-500">{doc.mime_type}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-zinc-600">{formatBytes(doc.size)}</td>
                  <td className="px-6 py-4 text-zinc-600">{format(new Date(doc.created_at), 'MMM d, yyyy')}</td>
                  <td className="px-6 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => handleRemoveFromGroup(doc)}
                      disabled={isSubmitting}
                      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-50"
                      title="Remove from group"
                    >
                      <FolderOutput className="h-4 w-4" />
                      Remove
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Modal isOpen={isUploadModalOpen} onClose={() => setIsUploadModalOpen(false)} title="Upload to Group">
        <form onSubmit={handleUpload} className="space-y-6">
          {uploadError && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{uploadError}</div>}
          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Select File</label>
            <Input type="file" name="file" required />
          </div>
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setIsUploadModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Uploading...' : 'Upload'}</Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={isMemberModalOpen} onClose={() => setIsMemberModalOpen(false)} title="Add Member">
        <div className="space-y-6">
          {memberError && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{memberError}</div>}

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Search Users</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <Input
                placeholder="Search by name or email..."
                className="pl-9"
                value={usersSearch}
                onChange={(e) => { setUsersSearch(e.target.value); setUsersPage(1); }}
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Select User</label>
            <div className="max-h-48 overflow-y-auto rounded-lg border border-zinc-200">
              {usersLoading ? (
                <div className="px-4 py-6 text-center text-sm text-zinc-500">Loading users...</div>
              ) : workspaceUsers.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-zinc-500">No users found</div>
              ) : (
                workspaceUsers.map((user) => {
                  const userId = user.user_id || user.id;
                  const isSelected = memberUserId === userId;
                  return (
                    <button
                      key={userId}
                      type="button"
                      onClick={() => setMemberUserId(userId)}
                      className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${isSelected ? 'bg-indigo-50' : 'hover:bg-zinc-50'}`}
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-xs font-medium text-zinc-600">
                        {(user.name || user.email || user.username || '?').charAt(0).toUpperCase()}
                      </div>
                      <div className="flex-1 overflow-hidden">
                        <p className="truncate text-sm font-medium text-zinc-900">{user.name || user.username || 'Unknown'}</p>
                        {user.email && <p className="truncate text-xs text-zinc-500">{user.email}</p>}
                      </div>
                      {isSelected && <div className="h-2 w-2 rounded-full bg-indigo-500" />}
                    </button>
                  );
                })
              )}
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-zinc-500">Page {usersPage} of {totalPages}</span>
                <div className="flex gap-1">
                  <Button type="button" variant="outline" size="sm" disabled={usersPage <= 1} onClick={() => setUsersPage((p) => p - 1)}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button type="button" variant="outline" size="sm" disabled={usersPage >= totalPages} onClick={() => setUsersPage((p) => p + 1)}>
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Or enter User ID manually</label>
            <Input
              placeholder="Enter user ID (UUID)"
              value={memberUserId}
              onChange={(e) => setMemberUserId(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Role</label>
            <select
              className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              value={memberRole}
              onChange={(e) => setMemberRole(e.target.value as 'member' | 'owner')}
            >
              <option value="member">Member (read, write, export)</option>
              <option value="owner">Owner (full access)</option>
            </select>
          </div>

          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setIsMemberModalOpen(false)}>Cancel</Button>
            <Button type="button" onClick={handleAddMember} disabled={isSubmitting || !memberUserId.trim()}>
              {isSubmitting ? 'Adding...' : 'Add Member'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
