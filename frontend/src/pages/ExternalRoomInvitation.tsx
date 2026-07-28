import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { format } from "date-fns";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Eye,
  FolderOpen,
  LogOut,
  Mail,
  Shield,
} from "lucide-react";
import { api } from "../services/api";
import {
  Document,
  ExternalRoomContext,
  ExternalRoomInviteInspection,
  NdaStatus,
} from "../types";
import { formatBytes } from "../lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { NdaGate } from "../components/NdaGate";
import { HexLogo } from "../components/ui/HexLogo";

export type ExternalRoomInvitationProps = {
  brandName?: string;
  homeHref?: string;
};

export function ExternalRoomInvitation({
  brandName = "Secure sharing",
  homeHref = "/",
}: ExternalRoomInvitationProps = {}) {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [inspection, setInspection] =
    useState<ExternalRoomInviteInspection | null>(null);
  const [context, setContext] = useState<ExternalRoomContext | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [docNda, setDocNda] = useState<{
    documentId: string;
    status: NdaStatus;
  } | null>(null);

  const loadSessionData =
    useCallback(async (): Promise<ExternalRoomContext> => {
      const nextContext = await api.getExternalRoomContext();
      setContext(nextContext);
      // The room-level NDA blocks the document list until accepted.
      if (nextContext.nda?.required && !nextContext.nda.accepted) {
        setDocuments([]);
      } else {
        setDocuments(await api.listExternalRoomDocuments());
      }
      return nextContext;
    }, []);

  const loadPage = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const invite = await api.inspectExternalRoomInvite(token);
      setInspection(invite);
      setEmail(invite.email);

      try {
        const currentContext = await loadSessionData();
        if (currentContext.room_id !== invite.room_id) {
          setContext(null);
          setDocuments([]);
          setInfo(
            `A different external room session is active for "${currentContext.room_name}". Starting this invitation will replace it.`,
          );
        }
      } catch {
        setContext(null);
        setDocuments([]);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load invitation",
      );
    } finally {
      setIsLoading(false);
    }
  }, [loadSessionData, token]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useEffect(() => {
    if (!info) return;
    const timer = window.setTimeout(() => setInfo(null), 3000);
    return () => window.clearTimeout(timer);
  }, [info]);

  const activeRoomName =
    context?.room_name || inspection?.room_name || "External room";
  const canDownload =
    context?.can_download || inspection?.can_download || false;

  async function handleCreateSession() {
    if (!token || !email.trim()) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await api.createExternalRoomSession(token, email.trim());
      await loadSessionData();
      setInfo("Room session started.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start room session",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDownload(documentId: string) {
    setError(null);
    try {
      const response = await api.getExternalRoomDocumentDownload(documentId);
      window.open(response.download_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to prepare download",
      );
    }
  }

  async function handleAcceptRoomNda(payload: {
    typed_name: string;
    scroll_confirmed: boolean;
    checkbox_confirmed: boolean;
  }) {
    const policy = context?.nda?.policy;
    if (!policy) return;
    await api.acceptExternalRoomNda({
      scope_type: policy.scope_type,
      scope_id: policy.scope_id,
      ...payload,
    });
    await loadSessionData();
    setInfo("NDA accepted. The room is now unlocked.");
  }

  async function handleOpenViewer(documentId: string) {
    setError(null);
    try {
      const session = await api.createExternalRoomDocumentSession(documentId);
      navigate(
        `/external-room/viewer/${encodeURIComponent(session.session_id)}`,
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to open protected viewer";
      if (message.includes("nda_acceptance_required")) {
        // The document itself carries an NDA — present it before opening.
        try {
          const statuses = await api.getExternalRoomNda(documentId);
          const outstanding = statuses.find(
            (s) =>
              s.required && !s.accepted && s.policy?.scope_type === "document",
          );
          if (outstanding) {
            setDocNda({ documentId, status: outstanding });
            return;
          }
        } catch {
          /* fall through to generic error */
        }
      }
      setError(message);
    }
  }

  async function handleAcceptDocNda(payload: {
    typed_name: string;
    scroll_confirmed: boolean;
    checkbox_confirmed: boolean;
  }) {
    if (!docNda?.status.policy) return;
    await api.acceptExternalRoomNda({
      scope_type: docNda.status.policy.scope_type,
      scope_id: docNda.status.policy.scope_id,
      ...payload,
    });
    const documentId = docNda.documentId;
    setDocNda(null);
    await handleOpenViewer(documentId);
  }

  async function handleLogout() {
    setError(null);
    try {
      await api.logoutExternalRoom();
      setContext(null);
      setDocuments([]);
      if (token) {
        const invite = await api.inspectExternalRoomInvite(token);
        setInspection(invite);
        setEmail(invite.email);
      }
      setInfo("Room session closed.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to close room session",
      );
    }
  }

  const documentCountLabel = useMemo(
    () => `${documents.length} document${documents.length === 1 ? "" : "s"}`,
    [documents.length],
  );
  const currentStep = !context
    ? 0
    : context.nda?.required && !context.nda.accepted
      ? 1
      : 2;

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f5f3ee] text-sm text-[#7a808a] dark:bg-[#171818] dark:text-zinc-500">
        Checking room access…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f5f3ee] text-[#101522] dark:bg-[#171818] dark:text-[#f3f1eb]">
      <header className="border-b border-black/10 bg-[#f5f3ee]/90 backdrop-blur-xl dark:border-white/10 dark:bg-[#171818]/90">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to={homeHref} className="flex items-center gap-3">
            <HexLogo className="h-8 w-8" />
            <span className="text-lg font-semibold tracking-tight">
              {brandName}
            </span>
          </Link>
          <Link
            to={homeHref}
            className="inline-flex items-center gap-2 text-sm text-[#626976] hover:text-[#101522] dark:text-zinc-400 dark:hover:text-white"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to {brandName}
          </Link>
          {context ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-[#626976] dark:text-zinc-400"
              onClick={() => void handleLogout()}
            >
              <LogOut className="mr-2 h-4 w-4" />
              End session
            </Button>
          ) : null}
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="mb-8 grid grid-cols-3 gap-2">
          {[
            ["01", "Verify identity"],
            ["02", "Review terms"],
            ["03", "Open room"],
          ].map(([number, label], index) => (
            <div
              key={number}
              className={`rounded-lg border px-3 py-3 ${
                index <= currentStep
                  ? "border-[#6657ff]/30 bg-[#f0eeff] dark:border-[#6657ff]/40 dark:bg-[#6657ff]/10"
                  : "border-black/10 bg-white/45 dark:border-white/10 dark:bg-white/[0.025]"
              }`}
            >
              <p className="text-xs font-semibold text-[#6657ff]">{number}</p>
              <p className="mt-1 text-xs font-medium text-[#626976] dark:text-zinc-400">
                {label}
              </p>
            </div>
          ))}
        </div>

        {info ? (
          <div className="mb-6 rounded-xl border border-emerald-300/60 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">
            {info}
          </div>
        ) : null}
        {error ? (
          <div className="mb-6 rounded-xl border border-red-300/60 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
            {error}
          </div>
        ) : null}

        {!context ? (
          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-start">
            <div className="max-w-2xl pt-2">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#4a3fe0] dark:text-[#a8a2ff]">
                Secure room invitation
              </p>
              <h1 className="mt-5 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">
                You’ve been invited to {activeRoomName}.
              </h1>
              <p className="mt-5 text-lg leading-relaxed text-[#626976] dark:text-zinc-400">
                Confirm the invited address to open this protected room. No
                account or password is required.
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                {[
                  "Access stays tied to the invited recipient",
                  canDownload
                    ? "Downloads are available where allowed"
                    : "Documents are view-only",
                  inspection?.can_print
                    ? "Printing is allowed"
                    : "Printing is restricted",
                  "Document activity may be visible to the sender",
                ].map((item) => (
                  <div
                    key={item}
                    className="flex items-start gap-3 rounded-xl border border-black/10 bg-white/55 p-4 text-sm text-[#626976] dark:border-white/10 dark:bg-white/[0.035] dark:text-zinc-400"
                  >
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#6657ff]" />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <Card className="border-black/10 bg-white/80 shadow-[0_24px_70px_rgba(16,21,34,0.08)] dark:border-white/10 dark:bg-[#202120] dark:shadow-black/20">
              <CardHeader>
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-lg bg-[#6657ff] text-white">
                  <Shield className="h-5 w-5" />
                </div>
                <CardTitle className="text-[#101522] dark:text-[#f3f1eb]">
                  Confirm your access
                </CardTitle>
                <CardDescription className="text-[#626976] dark:text-zinc-400">
                  Your email must match the address named in this invitation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="neutral">Room read</Badge>
                  {canDownload ? (
                    <Badge variant="neutral">Download</Badge>
                  ) : null}
                  {inspection?.can_print ? (
                    <Badge variant="neutral">Print flag</Badge>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-[#101522] dark:text-[#f3f1eb]">
                    Invited email
                  </label>
                  <Input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    readOnly={Boolean(inspection?.email)}
                    className="border-black/10 bg-[#f5f3ee] dark:border-white/10 dark:bg-[#171818]"
                  />
                </div>
                <div className="rounded-lg border border-black/10 bg-[#efedf7]/60 px-4 py-3 text-sm text-[#626976] dark:border-white/10 dark:bg-white/[0.035] dark:text-zinc-400">
                  This invitation expires{" "}
                  <span className="font-medium text-[#101522] dark:text-[#f3f1eb]">
                    {inspection?.expires_at
                      ? format(
                          new Date(inspection.expires_at),
                          "MMM d, yyyy h:mm a",
                        )
                      : "after its configured access window"}
                  </span>
                  .
                </div>
                <div>
                  <Button
                    className="w-full !bg-[#6657ff] !text-white hover:!bg-[#5548e8]"
                    onClick={() => void handleCreateSession()}
                    disabled={isSubmitting || !email.trim()}
                  >
                    {isSubmitting ? "Starting session..." : "Open room"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-[1fr_auto] lg:items-start">
              <Card className="border-black/10 bg-white/80 dark:border-white/10 dark:bg-[#202120]">
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#4a3fe0] dark:text-[#a8a2ff]">
                        Shared with you
                      </p>
                      <CardTitle className="text-[#101522] dark:text-[#f3f1eb]">
                        {context.room_name}
                      </CardTitle>
                      <CardDescription className="text-[#626976] dark:text-zinc-400">
                        Verified as {context.display_name || context.email}.
                        Access remains tied to this room and recipient identity.
                      </CardDescription>
                    </div>
                    <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#f0eeff] text-[#6657ff] dark:bg-[#6657ff]/15">
                      <FolderOpen className="h-6 w-6" />
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="success">Active room session</Badge>
                    <Badge variant="neutral">{documentCountLabel}</Badge>
                    {context.can_download ? (
                      <Badge variant="neutral">Download enabled</Badge>
                    ) : null}
                  </div>
                  <div className="rounded-lg border border-black/10 bg-[#efedf7]/60 px-4 py-3 text-sm text-[#626976] dark:border-white/10 dark:bg-white/[0.035] dark:text-zinc-400">
                    Opens, page activity, downloads, and agreement events may be
                    recorded and shown to the room owner.
                  </div>
                </CardContent>
              </Card>

              <Card className="border-black/10 bg-white/80 dark:border-white/10 dark:bg-[#202120] lg:w-80">
                <CardHeader>
                  <CardTitle className="text-[#101522] dark:text-[#f3f1eb]">
                    Your access
                  </CardTitle>
                  <CardDescription className="text-[#626976] dark:text-zinc-400">
                    Permissions attached to your verified identity.
                  </CardDescription>
                </CardHeader>
                <CardContent className="max-h-64 space-y-4 overflow-y-auto text-sm text-[#626976] dark:text-zinc-400">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f0eeff] text-[#6657ff] dark:bg-[#6657ff]/15">
                      <Shield className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-medium text-[#101522] dark:text-[#f3f1eb]">
                        {context.display_name || "Verified recipient"}
                      </p>
                      <p>{context.email}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="neutral">Room read</Badge>
                    {context.can_download ? (
                      <Badge variant="neutral">Download</Badge>
                    ) : null}
                    {context.can_print ? (
                      <Badge variant="neutral">Print</Badge>
                    ) : null}
                  </div>
                </CardContent>
              </Card>
            </div>

            {context.nda?.required && !context.nda.accepted ? (
              <NdaGate
                status={context.nda}
                pdfUrl={
                  context.nda.policy?.content_type === "pdf"
                    ? api.toAbsoluteApiUrl(
                        api.externalRoomNdaPdfUrl(
                          context.nda.policy.scope_type,
                          context.nda.policy.scope_id,
                        ),
                      )
                    : null
                }
                onAccept={handleAcceptRoomNda}
              />
            ) : (
              <Card className="border-black/10 bg-white/80 dark:border-white/10 dark:bg-[#202120]">
                <CardHeader>
                  <CardTitle className="text-[#101522] dark:text-[#f3f1eb]">
                    Room documents
                  </CardTitle>
                  <CardDescription className="text-[#626976] dark:text-zinc-400">
                    Documents made available to your verified access.
                  </CardDescription>
                </CardHeader>
                <CardContent className="max-h-[34rem] space-y-3 overflow-y-auto">
                  {documents.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-black/10 px-6 py-10 text-center text-sm text-[#7a808a] dark:border-white/10 dark:text-zinc-500">
                      No documents are currently visible in this room.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {documents.map((document) => (
                        <div
                          key={document.id}
                          className="flex flex-col gap-4 rounded-xl border border-black/10 bg-[#efedf7]/45 p-4 transition-colors hover:border-[#6657ff]/35 dark:border-white/10 dark:bg-white/[0.035] md:flex-row md:items-center md:justify-between"
                        >
                          <div className="min-w-0 space-y-1">
                            <p className="truncate font-medium text-[#101522] dark:text-[#f3f1eb]">
                              {document.name}
                            </p>
                            <div className="flex flex-wrap gap-3 text-xs text-[#7a808a] dark:text-zinc-500">
                              <span>{document.mime_type}</span>
                              <span>{formatBytes(document.size)}</span>
                              <span>
                                Uploaded{" "}
                                {format(
                                  new Date(document.created_at),
                                  "MMM d, yyyy",
                                )}
                              </span>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              className="!bg-[#6657ff] !text-white hover:!bg-[#5548e8]"
                              type="button"
                              size="sm"
                              onClick={() => void handleOpenViewer(document.id)}
                            >
                              <Eye className="mr-2 h-4 w-4" />
                              Open securely
                            </Button>
                            {context.can_download ? (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => void handleDownload(document.id)}
                              >
                                <Download className="mr-2 h-4 w-4" />
                                Download
                              </Button>
                            ) : (
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled
                              >
                                <Mail className="mr-2 h-4 w-4" />
                                View only
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        <p className="mt-10 text-center text-xs text-[#7a808a] dark:text-zinc-500">
          Protected by {brandName} · Recipient access remains scoped to this
          room.
        </p>
      </div>

      {docNda ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-900/60 p-4 py-10">
          <div className="w-full max-w-3xl">
            <div className="mb-3 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDocNda(null)}
              >
                Cancel
              </Button>
            </div>
            <NdaGate
              status={docNda.status}
              pdfUrl={
                docNda.status.policy?.content_type === "pdf"
                  ? api.toAbsoluteApiUrl(
                      api.externalRoomNdaPdfUrl(
                        docNda.status.policy.scope_type,
                        docNda.status.policy.scope_id,
                      ),
                    )
                  : null
              }
              onAccept={handleAcceptDocNda}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}