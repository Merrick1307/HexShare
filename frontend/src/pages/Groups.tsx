import type { FormEvent } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { Folder, Plus, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import { DocumentGroup } from '../types';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';

function GroupRowMenu({
  group,
  isOpen,
  onToggle,
  onEdit,
  onDelete,
}: {
  group: DocumentGroup;
  isOpen: boolean;
  onToggle: () => void;
  onEdit: (group: DocumentGroup) => void;
  onDelete: (group: DocumentGroup) => void;
}) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuContentRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setPos(null);
      return;
    }
    const update = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (rect) setPos({ top: rect.bottom + 8, left: rect.right - 160 }); // 160px = w-40
    };
    update();
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target) || menuContentRef.current?.contains(target)) return;
      onToggle();
    }
    document.addEventListener('mousedown', handleClick);
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [isOpen, onToggle]);

  return (
    <div className="relative inline-block text-left">
      <Button ref={buttonRef} type="button" variant="outline" size="sm" className="h-9 w-9 p-0" onClick={onToggle}>
        <MoreHorizontal className="h-4 w-4" />
      </Button>
      {isOpen && pos
        ? createPortal(
            <div
              ref={menuContentRef}
              style={{ position: 'fixed', top: pos.top, left: pos.left }}
              className="z-50 w-40 rounded-xl border border-zinc-200 bg-white p-1 shadow-xl"
            >
              <button
                type="button"
                onClick={() => onEdit(group)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-zinc-700 hover:bg-zinc-50"
              >
                <Pencil className="h-4 w-4" />
                Edit
              </button>
              <button
                type="button"
                onClick={() => onDelete(group)}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

export function Groups() {
  const containerRef = useRef<HTMLDivElement>(null);
  const {
    items: groups,
    total: groupsTotal,
    isLoading: groupsLoading,
    sentinelRef: groupsSentinelRef,
    reset: resetGroups,
  } = useInfiniteScroll<DocumentGroup>({
    fetchFn: (offset, limit) => api.listGroups(offset, limit),
    pageSize: 20,
    rootRef: containerRef,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<DocumentGroup | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState({ name: '', description: '' });

  const loadGroups = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      resetGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load groups');
    } finally {
      setIsLoading(false);
    }
  }, [resetGroups]);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    if (!successMessage) return;
    const timer = window.setTimeout(() => setSuccessMessage(null), 3500);
    return () => window.clearTimeout(timer);
  }, [successMessage]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!formData.name.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.createGroup({ name: formData.name.trim(), description: formData.description.trim() || undefined });
      // Refresh token to get updated policy with new group permissions
      await api.refreshToken();
      setIsCreateModalOpen(false);
      setFormData({ name: '', description: '' });
      setSuccessMessage('Group created successfully.');
      await loadGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create group');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleEdit(e: FormEvent) {
    e.preventDefault();
    if (!selectedGroup || !formData.name.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.updateGroup(selectedGroup.id, { name: formData.name.trim(), description: formData.description.trim() || undefined });
      setIsEditModalOpen(false);
      setSelectedGroup(null);
      setFormData({ name: '', description: '' });
      setSuccessMessage('Group updated successfully.');
      await loadGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update group');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!selectedGroup) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await api.deleteGroup(selectedGroup.id);
      setIsDeleteModalOpen(false);
      setSelectedGroup(null);
      setSuccessMessage('Group deleted successfully.');
      await loadGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete group');
    } finally {
      setIsSubmitting(false);
    }
  }

  function openEditModal(group: DocumentGroup) {
    setSelectedGroup(group);
    setFormData({ name: group.name, description: group.description || '' });
    setIsEditModalOpen(true);
  }

  function openDeleteModal(group: DocumentGroup) {
    setSelectedGroup(group);
    setIsDeleteModalOpen(true);
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-950">Groups</h1>
          <p className="mt-1 text-sm text-zinc-500">Organize documents into shared workspaces.</p>
        </div>
        <Button onClick={() => { setFormData({ name: '', description: '' }); setIsCreateModalOpen(true); }} className="gap-2">
          <Plus className="h-4 w-4" />
          New Group
        </Button>
      </div>

      {successMessage && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{successMessage}</div>}
      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div ref={containerRef} className="overflow-y-auto rounded-xl border border-zinc-200 bg-white shadow-sm max-h-[calc(100vh-16rem)]">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase text-zinc-500">
            <tr>
              <th className="px-6 py-4">Name</th>
              <th className="px-6 py-4">Description</th>
              <th className="px-6 py-4">Created</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {isLoading && groups.length === 0 ? (
              <tr><td colSpan={4} className="px-6 py-8 text-center text-zinc-500">Loading groups...</td></tr>
            ) : groups.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-12 text-center text-zinc-500">
                  <div className="flex flex-col items-center justify-center">
                    <Folder className="mb-3 h-10 w-10 text-zinc-300" />
                    <p className="text-base font-medium text-zinc-900">No groups yet</p>
                    <p className="mt-1 text-sm">Create a group to organize your documents.</p>
                  </div>
                </td>
              </tr>
            ) : (
              groups.map((group) => (
                <tr key={group.id} className="group transition-colors hover:bg-zinc-50/50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                        <Folder className="h-5 w-5" />
                      </div>
                      <Link to={`/groups/${group.id}`} className="font-medium text-zinc-900 hover:text-indigo-600 hover:underline">
                        {group.name}
                      </Link>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-zinc-600">{group.description || <span className="text-zinc-400">—</span>}</td>
                  <td className="px-6 py-4 text-zinc-600">{format(new Date(group.created_at), 'MMM d, yyyy')}</td>
                  <td className="px-6 py-4 text-right">
                    <GroupRowMenu
                      group={group}
                      isOpen={openMenuId === group.id}
                      onToggle={() => setOpenMenuId((current) => (current === group.id ? null : group.id))}
                      onEdit={openEditModal}
                      onDelete={openDeleteModal}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        <div ref={groupsSentinelRef} className="h-1" />
        {groupsLoading && groups.length > 0 ? (
          <div className="px-6 py-3 text-center text-sm text-zinc-400">Loading more groups...</div>
        ) : null}
      </div>

      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title="Create Group">
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-zinc-900">Name</label>
            <Input className="mt-1.5" value={formData.name} onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))} required />
          </div>
          <div>
            <label className="text-sm font-medium text-zinc-900">Description (optional)</label>
            <Input className="mt-1.5" value={formData.description} onChange={(e) => setFormData((d) => ({ ...d, description: e.target.value }))} />
          </div>
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setIsCreateModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Creating...' : 'Create'}</Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={isEditModalOpen} onClose={() => setIsEditModalOpen(false)} title="Edit Group">
        <form onSubmit={handleEdit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-zinc-900">Name</label>
            <Input className="mt-1.5" value={formData.name} onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))} required />
          </div>
          <div>
            <label className="text-sm font-medium text-zinc-900">Description</label>
            <Input className="mt-1.5" value={formData.description} onChange={(e) => setFormData((d) => ({ ...d, description: e.target.value }))} />
          </div>
          <div className="flex justify-end gap-3 border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={() => setIsEditModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Saving...' : 'Save'}</Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={isDeleteModalOpen} onClose={() => setIsDeleteModalOpen(false)} title="Delete Group">
        <p className="text-sm text-zinc-600">Are you sure you want to delete <strong>{selectedGroup?.name}</strong>? Documents in this group will become ungrouped.</p>
        <div className="mt-6 flex justify-end gap-3">
          <Button type="button" variant="outline" onClick={() => setIsDeleteModalOpen(false)}>Cancel</Button>
          <Button type="button" variant="danger" onClick={handleDelete} disabled={isSubmitting}>{isSubmitting ? 'Deleting...' : 'Delete'}</Button>
        </div>
      </Modal>
    </div>
  );
}
