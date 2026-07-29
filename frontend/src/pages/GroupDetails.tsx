import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { format } from 'date-fns';
import {
  ArrowLeft,
  ArrowDown,
  ArrowUp,
  Copy,
  ExternalLink,
  FileText,
  Folder,
  FolderOutput,
  Mail,
  Home,
  Search,
  Shield,
  Trash2,
  Upload,
  UserPlus,
  Plus,
  Pencil,
  ChevronLeft,
  ChevronRight,
  Users,
} from 'lucide-react';
import { api } from '../services/api';
import { Document, DocumentGroup, ExternalRoomGrant, ProvisionExternalRoomAccessResponse, RoomSection } from '../types';
import { parseApiDate } from '../lib/dateTime';
import { formatBytes } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { NdaAdminPanel } from '../components/NdaAdminPanel';
import { UploadQueue } from '../components/UploadQueue';
import { FileTypeIcon } from '../components/FileTypeIcon';

type WorkspaceUser = { id: string; user_id?: string; email?: string; name?: string; username?: string };

function statusForGrant(grant: ExternalRoomGrant) {
  if (grant.revoked_at) return { label: 'Revoked', variant: 'danger' as const };
  if (grant.expires_at && parseApiDate(grant.expires_at) <= new Date()) return { label: 'Expired', variant: 'warning' as const };
  return { label: 'Active', variant: 'success' as const };
}

type RoomAdminTab = 'home' | 'documents' | 'external-parties';

export function GroupDetails({ tabbedAdminView = false }: { tabbedAdminView?: boolean } = {}) {
  const { id } = useParams<{ id: string }>();
  const [group, setGroup] = useState<DocumentGroup | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [sections, setSections] = useState<RoomSection[]>([]);
  const [externalAccess, setExternalAccess] = useState<ExternalRoomGrant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadSectionId, setUploadSectionId] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMemberModalOpen, setIsMemberModalOpen] = useState(false);
  const [isExternalAccessModalOpen, setIsExternalAccessModalOpen] = useState(false);
  const [memberUserId, setMemberUserId] = useState('');
  const [memberRole, setMemberRole] = useState<'member' | 'owner'>('member');
  const [memberError, setMemberError] = useState<string | null>(null);
  const [workspaceUsers, setWorkspaceUsers] = useState<WorkspaceUser[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const [usersSearch, setUsersSearch] = useState('');
  const [usersLoading, setUsersLoading] = useState(false);
  const [externalAccessError, setExternalAccessError] = useState<string | null>(null);
  const [recipientEmail, setRecipientEmail] = useState('');
  const [recipientDisplayName, setRecipientDisplayName] = useState('');
  const [externalCanDownload, setExternalCanDownload] = useState(false);
  const [externalCanPrint, setExternalCanPrint] = useState(false);
  const [externalGrantDays, setExternalGrantDays] = useState(14);
  const [externalInviteDays, setExternalInviteDays] = useState(7);
  const [latestProvision, setLatestProvision] = useState<ProvisionExternalRoomAccessResponse | null>(null);
  const [copiedValue, setCopiedValue] = useState<string | null>(null);
  const [revokeAccessTarget, setRevokeAccessTarget] = useState<ExternalRoomGrant | null>(null);
  const [removeDocumentTarget, setRemoveDocumentTarget] = useState<Document | null>(null);
  const [revokeAccessError, setRevokeAccessError] = useState<string | null>(null);
  const [removeDocumentError, setRemoveDocumentError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<RoomAdminTab>('home');
  const [sectionEditor, setSectionEditor] = useState<{ mode: 'create' | 'rename'; section?: RoomSection } | null>(null);
  const [sectionName, setSectionName] = useState('');
  const [sectionEditorError, setSectionEditorError] = useState<string | null>(null);
  const [deleteSectionTarget, setDeleteSectionTarget] = useState<RoomSection | null>(null);
  const [deleteSectionError, setDeleteSectionError] = useState<string | null>(null);
  const [rotateInvitationTarget, setRotateInvitationTarget] = useState<{
    grant: ExternalRoomGrant;
    delivery: 'email' | 'return_link';
  } | null>(null);
  const [rotateInvitationError, setRotateInvitationError] = useState<string | null>(null);
  const PAGE_SIZE = 10;

  const loadData = useCallback(async (
    { showLoading = true }: { showLoading?: boolean } = {},
  ) => {
    if (!id) return;
    if (showLoading) {
      setIsLoading(true);
      setError(null);
    }
    try {
      const [groupData, docs, grants, roomSections] = await Promise.all([
        api.getGroup(id),
        api.listGroupDocuments(id),
        api.listExternalRoomAccess(id),
        api.listRoomSections(id),
      ]);
      setGroup(groupData);
      setDocuments(docs);
      setExternalAccess(grants);
      setSections(roomSections);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load room';
      if (showLoading) {
        setError(message);
      } else {
        setSuccessMessage(`Upload completed, but the room could not be refreshed: ${message}`);
      }
    } finally {
      if (showLoading) setIsLoading(false);
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

  const activeExternalAccessCount = useMemo(
    () => externalAccess.filter((grant) => !grant.revoked_at && (!grant.expires_at || parseApiDate(grant.expires_at) > new Date())).length,
    [externalAccess]
  );

  function openMemberModal() {
    setMemberUserId('');
    setMemberRole('member');
    setMemberError(null);
    setUsersPage(1);
    setUsersSearch('');
    setIsMemberModalOpen(true);
  }

  function openExternalAccessModal() {
    setRecipientEmail('');
    setRecipientDisplayName('');
    setExternalCanDownload(false);
    setExternalCanPrint(false);
    setExternalGrantDays(14);
    setExternalInviteDays(7);
    setExternalAccessError(null);
    setLatestProvision(null);
    setIsExternalAccessModalOpen(true);
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
      setSuccessMessage('Member added successfully.');
    } catch (err) {
      setMemberError(err instanceof Error ? err.message : 'Failed to add member');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleProvisionExternalAccess() {
    if (!id || !recipientEmail.trim()) return;
    setExternalAccessError(null);
    setIsSubmitting(true);
    try {
      const provision = await api.provisionExternalRoomAccess(id, {
        recipient_email: recipientEmail.trim(),
        recipient_display_name: recipientDisplayName.trim() || undefined,
        can_download: externalCanDownload,
        can_print: externalCanPrint,
        expires_in: externalGrantDays > 0 ? externalGrantDays * 24 * 60 * 60 : undefined,
        invite_expires_in: externalInviteDays * 24 * 60 * 60,
      });
      setLatestProvision(provision);
      setSuccessMessage('External room access provisioned.');
      setExternalAccess(await api.listExternalRoomAccess(id));
      setIsExternalAccessModalOpen(false);
    } catch (err) {
      setExternalAccessError(err instanceof Error ? err.message : 'Failed to provision external access');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRevokeExternalAccess() {
    if (!id || !revokeAccessTarget) return;
    setIsSubmitting(true);
    setRevokeAccessError(null);
    try {
      await api.revokeExternalRoomAccess(id, revokeAccessTarget.grant_id);
      setSuccessMessage('External room access revoked.');
      setRevokeAccessTarget(null);
      setExternalAccess(await api.listExternalRoomAccess(id));
    } catch (err) {
      setRevokeAccessError(err instanceof Error ? err.message : 'Failed to revoke external access');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRemoveFromGroup() {
    if (!removeDocumentTarget) return;
    setIsSubmitting(true);
    setRemoveDocumentError(null);
    try {
      await api.moveDocumentToGroup(removeDocumentTarget.id, null);
      setSuccessMessage('Document removed from room.');
      setRemoveDocumentTarget(null);
      await loadData();
    } catch (err) {
      setRemoveDocumentError(err instanceof Error ? err.message : 'Failed to remove document from room');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function copyToClipboard(value: string) {
    await navigator.clipboard.writeText(value);
    setCopiedValue(value);
    window.setTimeout(() => setCopiedValue(null), 1500);
  }

  function openCreateSection() {
    setSectionName('');
    setSectionEditorError(null);
    setSectionEditor({ mode: 'create' });
  }

  function openRenameSection(section: RoomSection) {
    setSectionName(section.name);
    setSectionEditorError(null);
    setSectionEditor({ mode: 'rename', section });
  }

  async function saveSection() {
    if (!id || !sectionEditor || isSubmitting) return;
    const name = sectionName.trim();
    if (!name) {
      setSectionEditorError('Enter a section name.');
      return;
    }
    if (sectionEditor.mode === 'rename' && name === sectionEditor.section?.name) {
      setSectionEditor(null);
      return;
    }
    setIsSubmitting(true);
    setSectionEditorError(null);
    try {
      if (sectionEditor.mode === 'create') {
        await api.createRoomSection(id, name.trim());
        setSuccessMessage('Section added.');
      } else if (sectionEditor.section) {
        await api.renameRoomSection(id, sectionEditor.section.id, name);
        setSuccessMessage('Section renamed.');
      }
      setSections(await api.listRoomSections(id));
      setSectionEditor(null);
    } catch (err) {
      setSectionEditorError(err instanceof Error ? err.message : 'Failed to save section');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function deleteSection() {
    if (!id || !deleteSectionTarget) return;
    setIsSubmitting(true);
    setDeleteSectionError(null);
    try {
      await api.deleteRoomSection(id, deleteSectionTarget.id);
      setDeleteSectionTarget(null);
      await loadData();
      setSuccessMessage('Section deleted; its documents are now Unsectioned.');
    } catch (err) {
      setDeleteSectionError(err instanceof Error ? err.message : 'Failed to delete section');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function moveSection(section: RoomSection, direction: -1 | 1) {
    if (!id) return;
    const ordered = [...sections].sort((a, b) => a.position - b.position);
    const index = ordered.findIndex((item) => item.id === section.id);
    const next = index + direction;
    if (next < 0 || next >= ordered.length) return;
    [ordered[index], ordered[next]] = [ordered[next], ordered[index]];
    try {
      setSections(await api.reorderRoomSections(id, ordered.map((item) => item.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder sections');
    }
  }

  async function moveDocumentToSection(document: Document, sectionId: string | null) {
    if (!id) return;
    try {
      await api.placeDocument(document.id, id, sectionId);
      await loadData();
      setSuccessMessage('Document moved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to move document');
    }
  }

  async function moveDocumentWithinSection(document: Document, direction: -1 | 1) {
    if (!id) return;
    const peers = documents
      .filter((item) => (item.room_section_id || null) === (document.room_section_id || null))
      .sort((a, b) => a.room_position - b.room_position);
    const index = peers.findIndex((item) => item.id === document.id);
    const next = index + direction;
    if (next < 0 || next >= peers.length) return;
    [peers[index], peers[next]] = [peers[next], peers[index]];
    try {
      await api.reorderRoomDocuments(id, document.room_section_id || null, peers.map((item) => item.id));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder documents');
    }
  }

  async function rotateInvitation(grant: ExternalRoomGrant, delivery: 'email' | 'return_link') {
    if (!id) return;
    setIsSubmitting(true);
    setRotateInvitationError(null);
    try {
      const result = await api.reissueExternalRoomInvitation(id, grant.grant_id, delivery);
      if (delivery === 'return_link') {
        await copyToClipboard(api.toAbsoluteFrontendUrl(result.invite_path));
        setSuccessMessage('A fresh invitation link was copied. The previous invitation link is now invalid.');
      } else {
        if (result.email_sent) {
          setSuccessMessage('Invitation resent. The previous invitation link is now invalid.');
        } else {
          try {
            await copyToClipboard(api.toAbsoluteFrontendUrl(result.invite_path));
            setSuccessMessage('Email delivery failed, so the fresh invitation link was copied instead.');
          } catch {
            setError('The invitation was rotated, but email delivery and automatic copying failed.');
          }
        }
      }
      setExternalAccess(await api.listExternalRoomAccess(id));
      setRotateInvitationTarget(null);
    } catch (err) {
      setRotateInvitationError(err instanceof Error ? err.message : 'Failed to rotate invitation');
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
          <ArrowLeft className="h-4 w-4" /> Back to Rooms
        </Link>
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error || 'Room not found'}</div>
      </div>
    );
  }

  const latestInviteUrl = latestProvision ? api.toAbsoluteFrontendUrl(latestProvision.invite_path) : null;

  return (
    <div className="space-y-6 sm:space-y-8">
      <div>
        <Link to="/groups" className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900">
          <ArrowLeft className="h-4 w-4" /> Back to Rooms
        </Link>
      </div>

      <div className="flex flex-col items-stretch justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-3 sm:gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 sm:h-14 sm:w-14">
            <Folder className="h-7 w-7" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-zinc-950">{group.name}</h1>
            {group.description && <p className="mt-1 text-sm text-zinc-500">{group.description}</p>}
          </div>
        </div>
        {!tabbedAdminView ? <div className="grid gap-2 sm:flex sm:flex-wrap sm:gap-3">
          <Button variant="outline" onClick={openMemberModal} className="w-full gap-2 sm:w-auto">
            <UserPlus className="h-4 w-4" />
            Add Member
          </Button>
          <Button variant="outline" onClick={openExternalAccessModal} className="w-full gap-2 sm:w-auto">
            <Mail className="h-4 w-4" />
            Invite External
          </Button>
          <Button onClick={() => { setUploadSectionId(''); setIsUploadModalOpen(true); }} className="w-full gap-2 sm:w-auto">
            <Upload className="h-4 w-4" />
            Upload to Room
          </Button>
        </div> : null}
      </div>

      {successMessage && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{successMessage}</div>}

      {tabbedAdminView ? (
        <div className="overflow-x-auto border-b border-zinc-200">
          <div className="-mb-px flex min-w-max gap-4 sm:gap-6" role="tablist" aria-label="Room administration">
            {([
              { id: 'home', label: 'Home', icon: Home },
              { id: 'documents', label: 'Documents', icon: FileText },
              { id: 'external-parties', label: 'External Parties', icon: Users },
            ] as const).map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-indigo-600 text-indigo-700'
                      : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-900'
                  }`}
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {(!tabbedAdminView || activeTab === 'home') ? (
        <div className="space-y-6" role={tabbedAdminView ? 'tabpanel' : undefined}>
          {tabbedAdminView ? (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                  <p className="text-sm text-zinc-500">Documents</p>
                  <p className="mt-2 text-2xl font-semibold text-zinc-950">{documents.length}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                  <p className="text-sm text-zinc-500">Sections</p>
                  <p className="mt-2 text-2xl font-semibold text-zinc-950">{sections.length}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm">
                  <p className="text-sm text-zinc-500">Active external parties</p>
                  <p className="mt-2 text-2xl font-semibold text-zinc-950">{activeExternalAccessCount}</p>
                </div>
              </div>
              <div className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 className="font-semibold text-zinc-950">Internal room access</h2>
                  <p className="mt-1 text-sm text-zinc-500">Add a workspace member who should help manage this room.</p>
                </div>
                <Button variant="outline" onClick={openMemberModal} className="w-full shrink-0 gap-2 sm:w-auto">
                  <UserPlus className="h-4 w-4" />
                  Add Member
                </Button>
              </div>
            </>
          ) : null}
          {id ? <NdaAdminPanel scope="room" id={id} /> : null}
        </div>
      ) : null}

      {(!tabbedAdminView || activeTab === 'external-parties') && latestProvision && latestInviteUrl ? (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-4 text-sm text-indigo-900">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-1">
              <p className="font-medium">Invitation ready</p>
              <p>
                {latestProvision.display_name || latestProvision.email} can bootstrap room access with this invitation URL.
              </p>
              <p className="break-all font-mono text-xs text-indigo-800">{latestInviteUrl}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => void copyToClipboard(latestInviteUrl)}>
                <Copy className="mr-2 h-4 w-4" />
                {copiedValue === latestInviteUrl ? 'Copied' : 'Copy'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => window.open(latestInviteUrl, '_blank', 'noopener,noreferrer')}>
                <ExternalLink className="mr-2 h-4 w-4" />
                Open
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {(!tabbedAdminView || activeTab === 'documents') ? <div className="space-y-4" role={tabbedAdminView ? 'tabpanel' : undefined}>
        <div className="flex flex-col items-stretch justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">Room documents</h2>
            <p className="text-sm text-zinc-500">Sections and document order are shown to recipients exactly as arranged here.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {tabbedAdminView ? (
              <Button type="button" size="sm" onClick={() => { setUploadSectionId(''); setIsUploadModalOpen(true); }}>
                <Upload className="mr-2 h-4 w-4" /> Upload
              </Button>
            ) : null}
            <Button type="button" variant="outline" size="sm" onClick={openCreateSection}>
              <Plus className="mr-2 h-4 w-4" /> Add section
            </Button>
          </div>
        </div>
        {documents.length === 0 && sections.length === 0 ? (
          <div className="rounded-xl border border-zinc-200 bg-white px-6 py-12 text-center text-zinc-500 shadow-sm">
            <FileText className="mx-auto mb-3 h-10 w-10 text-zinc-300" />
            <p className="text-base font-medium text-zinc-900">No documents in this room</p>
            <p className="mt-1 text-sm">Add a section or upload documents to get started.</p>
          </div>
        ) : null}
        {[...sections.map((section) => ({ id: section.id, name: section.name, section })), { id: null, name: 'Unsectioned', section: null }].map((bucket) => {
          const bucketDocuments = documents
            .filter((document) => (document.room_section_id || null) === bucket.id)
            .sort((a, b) => a.room_position - b.room_position);
          if (!bucket.section && bucketDocuments.length === 0) return null;
          return (
            <section key={bucket.id || 'unsectioned'} className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 bg-zinc-50 px-4 py-3">
                <div>
                  <h3 className="font-medium text-zinc-900">{bucket.name}</h3>
                  <p className="text-xs text-zinc-500">{bucketDocuments.length} document{bucketDocuments.length === 1 ? '' : 's'}</p>
                </div>
                <div className="flex items-center gap-1">
                  <Button type="button" variant="outline" size="sm" onClick={() => { setUploadSectionId(bucket.id || ''); setIsUploadModalOpen(true); }}>
                    <Upload className="mr-2 h-4 w-4" /> Upload here
                  </Button>
                  {bucket.section ? (
                    <>
                      <button type="button" title="Move section up" onClick={() => void moveSection(bucket.section!, -1)} className="rounded p-2 text-zinc-500 hover:bg-white"><ArrowUp className="h-4 w-4" /></button>
                      <button type="button" title="Move section down" onClick={() => void moveSection(bucket.section!, 1)} className="rounded p-2 text-zinc-500 hover:bg-white"><ArrowDown className="h-4 w-4" /></button>
                      <button type="button" title="Rename section" onClick={() => openRenameSection(bucket.section!)} className="rounded p-2 text-zinc-500 hover:bg-white"><Pencil className="h-4 w-4" /></button>
                      <button type="button" title="Delete section" onClick={() => { setDeleteSectionError(null); setDeleteSectionTarget(bucket.section!); }} className="rounded p-2 text-red-500 hover:bg-red-50"><Trash2 className="h-4 w-4" /></button>
                    </>
                  ) : null}
                </div>
              </div>
              {bucketDocuments.length === 0 ? <p className="px-4 py-6 text-center text-sm text-zinc-400">No documents in this section.</p> : (
                <ul className="divide-y divide-zinc-100">
                  {bucketDocuments.map((doc, index) => (
                    <li key={doc.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <FileTypeIcon fileName={doc.name} mimeType={doc.mime_type} size="sm" />
                      <div className="min-w-0 flex-1">
                        <Link to={`/documents/${doc.id}`} className="truncate font-medium text-zinc-900 hover:text-indigo-600 hover:underline">{doc.name}</Link>
                        <p className="text-xs text-zinc-500">{formatBytes(doc.size)} · {doc.protection?.label} · {format(parseApiDate(doc.created_at), 'MMM d, yyyy')}</p>
                      </div>
                      <select
                        aria-label={`Move ${doc.name} to section`}
                        className="order-last w-full rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-xs sm:order-none sm:w-auto"
                        value={doc.room_section_id || ''}
                        onChange={(event) => void moveDocumentToSection(doc, event.target.value || null)}
                      >
                        <option value="">Unsectioned</option>
                        {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
                      </select>
                      <button type="button" disabled={index === 0} title="Move document up" onClick={() => void moveDocumentWithinSection(doc, -1)} className="rounded p-1.5 text-zinc-500 disabled:opacity-30"><ArrowUp className="h-4 w-4" /></button>
                      <button type="button" disabled={index === bucketDocuments.length - 1} title="Move document down" onClick={() => void moveDocumentWithinSection(doc, 1)} className="rounded p-1.5 text-zinc-500 disabled:opacity-30"><ArrowDown className="h-4 w-4" /></button>
                      <button type="button" onClick={() => { setRemoveDocumentError(null); setRemoveDocumentTarget(doc); }} title="Remove from room" className="rounded p-1.5 text-zinc-500 hover:text-red-600"><FolderOutput className="h-4 w-4" /></button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div> : null}

      {(!tabbedAdminView || activeTab === 'external-parties') ? <div className="rounded-xl border border-zinc-200 bg-white shadow-sm" role={tabbedAdminView ? 'tabpanel' : undefined}>
        <div className="flex flex-col items-stretch justify-between gap-4 border-b border-zinc-200 px-4 py-5 sm:flex-row sm:items-start sm:px-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-950">External access</h2>
              <Badge variant={activeExternalAccessCount > 0 ? 'success' : 'neutral'}>{activeExternalAccessCount} active</Badge>
            </div>
            <p className="mt-1 text-sm text-zinc-500">
              Provisioned room access for external recipients. Each recipient gets an invitation bootstrap and a room-scoped session.
            </p>
          </div>
          <Button onClick={openExternalAccessModal} className="w-full shrink-0 gap-2 sm:w-auto">
            <Mail className="h-4 w-4" />
            Invite External
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase text-zinc-500">
              <tr>
                <th className="px-6 py-4">Recipient</th>
                <th className="px-6 py-4">Access</th>
                <th className="px-6 py-4">Grant window</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200">
              {externalAccess.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-zinc-500">
                    <div className="flex flex-col items-center justify-center">
                      <Shield className="mb-3 h-10 w-10 text-zinc-300" />
                      <p className="text-base font-medium text-zinc-900">No external room access yet</p>
                      <p className="mt-1 text-sm">Invite a recipient to provision a room-scoped external session.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                externalAccess.map((grant) => {
                  const status = statusForGrant(grant);
                  return (
                    <tr key={grant.grant_id} className="transition-colors hover:bg-zinc-50/50">
                      <td className="px-6 py-4">
                        <div className="space-y-1">
                          <p className="font-medium text-zinc-900">{grant.display_name || 'Unnamed recipient'}</p>
                          <p className="text-xs text-zinc-500">{grant.email}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="neutral">Room read</Badge>
                          {grant.can_download ? <Badge variant="neutral">Download</Badge> : null}
                          {grant.can_print ? <Badge variant="neutral">Print</Badge> : null}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-zinc-600">
                        <div className="space-y-1">
                          <p>Granted {format(parseApiDate(grant.granted_at), 'MMM d, yyyy')}</p>
                          <p className="text-xs text-zinc-500">
                            {grant.expires_at ? `Expires ${format(parseApiDate(grant.expires_at), 'MMM d, yyyy h:mm a')}` : 'No grant expiry'}
                          </p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <Badge variant={status.variant}>{status.label}</Badge>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {status.label === 'Active' ? (
                          <div className="flex flex-wrap justify-end gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!!grant.resend_available_at && parseApiDate(grant.resend_available_at) > new Date()}
                              title={grant.resend_available_at ? `Available ${format(parseApiDate(grant.resend_available_at), 'MMM d, h:mm a')}` : undefined}
                              onClick={() => {
                                setRotateInvitationError(null);
                                setRotateInvitationTarget({ grant, delivery: 'email' });
                              }}
                            >
                              <Mail className="mr-2 h-4 w-4" /> Resend
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!!grant.resend_available_at && parseApiDate(grant.resend_available_at) > new Date()}
                              onClick={() => {
                                setRotateInvitationError(null);
                                setRotateInvitationTarget({ grant, delivery: 'return_link' });
                              }}
                            >
                              <Copy className="mr-2 h-4 w-4" /> Copy invitation
                            </Button>
                            <Button type="button" variant="outline" size="sm" onClick={() => { setRevokeAccessError(null); setRevokeAccessTarget(grant); }}>
                              <Trash2 className="mr-2 h-4 w-4" /> Revoke
                            </Button>
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div> : null}

      <Modal
        isOpen={sectionEditor !== null}
        onClose={() => {
          setSectionEditor(null);
          setSectionEditorError(null);
        }}
        title={sectionEditor?.mode === 'rename' ? 'Rename section' : 'Add section'}
      >
        <div className="space-y-5">
          {sectionEditorError ? (
            <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {sectionEditorError}
            </div>
          ) : null}
          <div className="space-y-2">
            <label htmlFor="room-section-name" className="text-sm font-medium text-zinc-900">Section name</label>
            <Input
              id="room-section-name"
              autoFocus
              maxLength={120}
              value={sectionName}
              onChange={(event) => setSectionName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void saveSection();
              }}
              placeholder="Financials"
            />
          </div>
          <div className="flex flex-col-reverse gap-3 border-t border-zinc-100 pt-4 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="outline"
              disabled={isSubmitting}
              onClick={() => {
                setSectionEditor(null);
                setSectionEditorError(null);
              }}
            >
              Cancel
            </Button>
            <Button type="button" disabled={isSubmitting} onClick={() => void saveSection()}>
              {isSubmitting ? 'Saving...' : 'Save section'}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteSectionTarget !== null}
        title="Delete section"
        description={
          deleteSectionTarget
            ? `Delete "${deleteSectionTarget.name}"? Its documents will move to Unsectioned.`
            : ''
        }
        confirmLabel="Delete section"
        error={deleteSectionError}
        isConfirming={isSubmitting}
        onCancel={() => {
          setDeleteSectionTarget(null);
          setDeleteSectionError(null);
        }}
        onConfirm={() => void deleteSection()}
      />

      <ConfirmDialog
        isOpen={rotateInvitationTarget !== null}
        title={rotateInvitationTarget?.delivery === 'email' ? 'Resend invitation' : 'Create a fresh invitation link'}
        description={
          rotateInvitationTarget
            ? `This will ${
                rotateInvitationTarget.delivery === 'email' ? 'resend the invitation to' : 'create a copyable invitation link for'
              } ${rotateInvitationTarget.grant.email} and invalidate the previous invitation link. Active recipient sessions stay valid.`
            : ''
        }
        confirmLabel={rotateInvitationTarget?.delivery === 'email' ? 'Resend invitation' : 'Create link'}
        error={rotateInvitationError}
        isConfirming={isSubmitting}
        variant="primary"
        onCancel={() => {
          setRotateInvitationTarget(null);
          setRotateInvitationError(null);
        }}
        onConfirm={() => {
          if (rotateInvitationTarget) {
            void rotateInvitation(rotateInvitationTarget.grant, rotateInvitationTarget.delivery);
          }
        }}
      />

      <Modal isOpen={isUploadModalOpen} onClose={() => setIsUploadModalOpen(false)} title="Upload to room">
        <div className="space-y-5">
          <div>
            <label className="text-sm font-medium text-zinc-900">Destination section</label>
            <select
              className="mt-1.5 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm"
              value={uploadSectionId}
              onChange={(event) => setUploadSectionId(event.target.value)}
            >
              <option value="">Unsectioned</option>
              {sections.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}
            </select>
          </div>
          {id ? (
            <UploadQueue
              roomId={id}
              sectionId={uploadSectionId || undefined}
              onClose={() => setIsUploadModalOpen(false)}
              onSettled={async ({ successful, failed }) => {
                if (successful) {
                  setSuccessMessage(`${successful} document${successful === 1 ? '' : 's'} uploaded${failed ? `; ${failed} failed` : ''}.`);
                  // Keep the upload queue mounted while refreshing so its
                  // completion dialog can offer OK or Continue uploading.
                  await loadData({ showLoading: false });
                }
              }}
            />
          ) : null}
        </div>
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

          <div className="flex flex-col-reverse gap-3 border-t border-zinc-100 pt-4 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => setIsMemberModalOpen(false)}>Cancel</Button>
            <Button type="button" onClick={handleAddMember} disabled={isSubmitting || !memberUserId.trim()}>
              {isSubmitting ? 'Adding...' : 'Add Member'}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={isExternalAccessModalOpen} onClose={() => setIsExternalAccessModalOpen(false)} title="Provision external room access">
        <div className="space-y-6">
          {externalAccessError && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{externalAccessError}</div>}

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Recipient email</label>
            <Input
              type="email"
              placeholder="james@example.com"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-zinc-900">Display name</label>
            <Input
              placeholder="James Okafor"
              value={recipientDisplayName}
              onChange={(e) => setRecipientDisplayName(e.target.value)}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900">Grant expiry (days)</label>
              <Input
                type="number"
                min={1}
                max={365}
                value={externalGrantDays}
                onChange={(e) => setExternalGrantDays(Number(e.target.value) || 1)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-zinc-900">Invite expiry (days)</label>
              <Input
                type="number"
                min={1}
                max={30}
                value={externalInviteDays}
                onChange={(e) => setExternalInviteDays(Number(e.target.value) || 1)}
              />
            </div>
          </div>

          <div className="space-y-3">
            <label className="text-sm font-medium text-zinc-900">Permissions</label>
            <label className="flex items-center gap-3 text-sm text-zinc-700">
              <input type="checkbox" checked={externalCanDownload} onChange={(e) => setExternalCanDownload(e.target.checked)} />
              <span>Allow document download inside this room</span>
            </label>
            <label className="flex items-center gap-3 text-sm text-zinc-700">
              <input type="checkbox" checked={externalCanPrint} onChange={(e) => setExternalCanPrint(e.target.checked)} />
              <span>Allow print flag on the grant</span>
            </label>
          </div>
          {documents.some((document) => document.protection?.download_required) && !externalCanDownload ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              This room contains download-only documents. Those files will remain listed, but the recipient cannot open them unless document download is allowed.
            </div>
          ) : null}

          <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-600">
            The invitation URL only bootstraps the room session. Durable access stays on the provisioned room grant.
          </div>

          <div className="flex flex-col-reverse gap-3 border-t border-zinc-100 pt-4 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => setIsExternalAccessModalOpen(false)}>Cancel</Button>
            <Button type="button" onClick={handleProvisionExternalAccess} disabled={isSubmitting || !recipientEmail.trim()}>
              {isSubmitting ? 'Provisioning...' : 'Provision access'}
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!revokeAccessTarget}
        title="Revoke external access"
        description={
          revokeAccessTarget
            ? `Revoke room access for "${revokeAccessTarget.display_name || revokeAccessTarget.email}"? This recipient will no longer be able to use this room grant.`
            : ''
        }
        confirmLabel="Revoke access"
        error={revokeAccessError}
        isConfirming={isSubmitting}
        onCancel={() => { setRevokeAccessTarget(null); setRevokeAccessError(null); }}
        onConfirm={() => void handleRevokeExternalAccess()}
      />

      <ConfirmDialog
        isOpen={!!removeDocumentTarget}
        title="Remove document from room"
        description={
          removeDocumentTarget
            ? `Remove "${removeDocumentTarget.name}" from this room? The document will stay in your workspace.`
            : ''
        }
        confirmLabel="Remove"
        error={removeDocumentError}
        isConfirming={isSubmitting}
        variant="primary"
        onCancel={() => { setRemoveDocumentTarget(null); setRemoveDocumentError(null); }}
        onConfirm={() => void handleRemoveFromGroup()}
      />
    </div>
  );
}
