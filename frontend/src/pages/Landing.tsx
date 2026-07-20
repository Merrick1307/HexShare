import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  Clock3,
  Eye,
  FolderOpen,
  Github,
  Link2,
  Lock,
  Mail,
  MessageSquare,
  Shield,
  Upload,
  Users,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { HexLogo } from '../components/ui/HexLogo';

const repoUrl = 'https://github.com/Merrick1307/HexShare';
const issuesUrl = `${repoUrl}/issues`;

const productHighlights = [
  {
    title: 'Direct upload flow',
    description: 'Upload files securely, finalize them in your workspace, and keep document handling on a controlled backend path.',
    icon: Upload,
  },
  {
    title: 'Document rooms',
    description: 'Organize documents into shared rooms so the right people can access the right material.',
    icon: FolderOpen,
  },
  {
    title: 'Share link controls',
    description: 'Set expiry, limit downloads and printing, and add recipient checks before a document is opened.',
    icon: Link2,
  },
  {
    title: 'Secure viewer sessions',
    description: 'Deliver protected viewing sessions instead of exposing documents through unrestricted raw file access.',
    icon: Eye,
  },
  {
    title: 'Revocation and policy checks',
    description: 'Cut off access when a link expires or is revoked, with backend-enforced policy checks and token invalidation.',
    icon: Shield,
  },
  {
    title: 'Document analytics',
    description: 'See who opened a document, how often it was viewed, and how engagement changed over time.',
    icon: BarChart3,
  },
];

const workflowSteps = [
  {
    step: '01',
    title: 'Upload the document',
    description: 'Add a file to your workspace and place it where it belongs from the start.',
  },
  {
    step: '02',
    title: 'Set access rules',
    description: 'Choose how long access lasts and what recipients are allowed to do with the file.',
  },
  {
    step: '03',
    title: 'Share a protected link',
    description: 'Send a link that opens a secure viewing experience built for controlled delivery.',
  },
  {
    step: '04',
    title: 'Track and revoke',
    description: 'Monitor activity, review engagement, and disable access the moment you need to.',
  },
];

const productSurfaces = [
  {
    title: 'Documents workspace',
    description: 'Manage uploads, search your library, move files between rooms, and create links from one place.',
  },
  {
    title: 'Room management',
    description: 'Create shared spaces for teams, projects, or clients and control membership at the room level.',
  },
  {
    title: 'Document details',
    description: 'Open a document page to review details, manage links, and check analytics without leaving context.',
  },
  {
    title: 'Protected viewing',
    description: 'Give recipients a cleaner, safer way to review shared content with session-aware protection.',
  },
];

const comingSoonFeatures = [
  {
    title: 'External party identity',
    description: 'Stronger recipient identity flows for outside parties, building on the email-gated access path that already exists today.',
    icon: Users,
  },
  {
    title: 'Q&A workflows',
    description: 'Structured question-and-answer threads around shared documents so review can stay attached to the material.',
    icon: MessageSquare,
  },
  {
    title: 'AI-enabled Q&A',
    description: 'Document-aware AI assistance for guided answers, follow-up questions, and faster review workflows.',
    icon: BrainCircuit,
  },
];

const aboutPoints = [
  {
    title: 'What it is',
    description: 'HexShare is built for teams that need to share important documents without losing control once a link leaves the workspace.',
  },
  {
    title: 'Where it runs',
    description: 'It is designed for self-hosted deployments backed by PostgreSQL, Redis, and S3-compatible object storage.',
  },
  {
    title: 'How access works',
    description: 'OIDC login, permissions, and access checks stay on the backend so sharing rules remain enforceable after a link is sent.',
  },
];

const faqItems = [
  {
    question: 'Is HexShare a general-purpose cloud drive?',
    answer: 'No. HexShare is built for controlled document delivery, protected viewing, and visibility after sharing.',
  },
  {
    question: 'What can users do in the app today?',
    answer: 'Users can upload documents, organize them into rooms, share protected links, inspect analytics, and revoke access.',
  },
  {
    question: 'Can HexShare be self-hosted?',
    answer: 'Yes. The project is built around a self-hosted stack with PostgreSQL, Redis, S3-compatible storage, and optional HexIAM integration for identity and policy.',
  },
  {
    question: 'How do recipients view shared files?',
    answer: 'Recipients open a protected link that takes them into a secure viewing flow instead of a plain file download page.',
  },
  {
    question: 'Where should technical questions or contribution discussions go?',
    answer: 'GitHub is the best place for technical questions, bug reports, and contribution discussions.',
  },
];

function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} className="text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900">
      {label}
    </a>
  );
}

export function Landing() {
  return (
    <div className="min-h-screen bg-white text-zinc-950">
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-6xl items-center justify-between px-6 lg:px-8">
          <Link to="/" className="flex items-center gap-3 text-zinc-950">
            <HexLogo className="h-9 w-9" />
            <span className="text-xl font-semibold tracking-tight">HexShare</span>
          </Link>

          <nav className="hidden items-center gap-6 md:flex">
            <NavLink href="#features" label="Features" />
            <NavLink href="#workflow" label="Workflow" />
            <NavLink href="#roadmap" label="Coming Soon" />
            <NavLink href="#about" label="About" />
            <NavLink href="#faq" label="FAQ" />
            <NavLink href="#contact" label="Contact" />
          </nav>

          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900">
              Sign In
            </Link>
            <Link to="/signup">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="border-b border-zinc-200">
          <div className="mx-auto grid max-w-6xl gap-14 px-6 py-20 lg:grid-cols-[1.1fr_0.9fr] lg:px-8 lg:py-28">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-zinc-600">
                <Lock className="h-3.5 w-3.5" />
                Self-hosted secure document delivery
              </div>
              <h1 className="mt-6 text-5xl font-semibold tracking-tight text-zinc-950 sm:text-6xl">
                Share sensitive documents without giving up control.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600">
                HexShare gives teams a self-hosted workspace for protected document delivery. Upload files, organize
                them into rooms, enforce OIDC-backed access, and keep visibility after a link is sent.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link to="/signup">
                  <Button size="lg" className="w-full gap-2 sm:w-auto">
                    Create workspace
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link to="/login">
                  <Button size="lg" variant="outline" className="w-full sm:w-auto">
                    Open existing workspace
                  </Button>
                </Link>
              </div>
              <div className="mt-10 grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">Protected links</p>
                  <p className="mt-2 text-sm text-zinc-700">Share documents with expiry, permission, and recipient controls.</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">OIDC-backed access</p>
                  <p className="mt-2 text-sm text-zinc-700">Keep authentication and policy enforcement on the backend.</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">View analytics</p>
                  <p className="mt-2 text-sm text-zinc-700">Track activity, monitor engagement, and revoke access when needed.</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-zinc-950 p-6 text-zinc-50 shadow-sm">
              <div className="flex items-center justify-between gap-4 border-b border-zinc-800 pb-4">
                <div>
                  <p className="text-sm font-semibold">Built for the full sharing flow</p>
                  <p className="mt-1 text-xs text-zinc-400">From upload to audited delivery</p>
                </div>
                <div className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-300">HexShare</div>
              </div>

              <div className="mt-6 space-y-4">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">Upload and organize</p>
                  <p className="mt-2 text-sm text-zinc-200">Keep documents structured with shared rooms and a workspace built for ongoing access management.</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">Share with precision</p>
                  <p className="mt-2 text-sm text-zinc-200">Decide who can open a file, how long access lasts, and whether recipients can download or print.</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">Track every handoff</p>
                  <p className="mt-2 text-sm text-zinc-200">Follow engagement, review viewer activity, and revoke access when the document should no longer circulate.</p>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-black/40 p-4 font-mono text-sm text-zinc-300">
                  <p>Upload. Share. Track. Revoke.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="features" className="bg-zinc-50 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Features</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                Everything you need to control document access.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-zinc-600">
                HexShare brings uploads, permissions, protected delivery, and visibility into a single self-hosted sharing workflow.
              </p>
            </div>

            <div className="mt-14 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
              {productHighlights.map((item) => {
                const Icon = item.icon;

                return (
                  <Card key={item.title} className="border-zinc-200">
                    <CardContent className="p-6">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-200 bg-white">
                        <Icon className="h-5 w-5 text-zinc-900" />
                      </div>
                      <h3 className="mt-5 text-lg font-semibold tracking-tight text-zinc-950">{item.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-zinc-600">{item.description}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </section>

        <section id="workflow" className="border-t border-zinc-200 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Workflow</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                A sharing flow that stays under control.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-zinc-600">
                From the first upload to the final view, every step is built around secure delivery, clear ownership, and revocable access.
              </p>
            </div>

            <div className="mt-14 grid gap-6 lg:grid-cols-4">
              {workflowSteps.map((item) => (
                <div key={item.step} className="rounded-xl border border-zinc-200 bg-white p-6">
                  <p className="text-sm font-semibold text-zinc-400">{item.step}</p>
                  <h3 className="mt-4 text-lg font-semibold tracking-tight text-zinc-950">{item.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-zinc-600">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-zinc-200 bg-zinc-950 px-6 py-20 text-zinc-50 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-400">Product surfaces</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
                Designed for the work that happens after the file is sent.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-zinc-400">
                HexShare gives teams practical tools for document management, protected sharing, and follow-through.
              </p>
            </div>

            <div className="mt-14 grid gap-6 md:grid-cols-2">
              {productSurfaces.map((surface) => (
                <div key={surface.title} className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
                  <h3 className="text-lg font-semibold tracking-tight text-zinc-100">{surface.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-zinc-400">{surface.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="roadmap" className="border-t border-zinc-200 bg-zinc-50 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Coming soon</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                The next workflows on the product path.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-zinc-600">
                The current release is focused on controlled delivery, protected viewing, and access enforcement. The next layer extends that into richer collaboration and recipient identity workflows.
              </p>
            </div>

            <div className="mt-14 grid gap-6 md:grid-cols-3">
              {comingSoonFeatures.map((item) => {
                const Icon = item.icon;

                return (
                  <Card key={item.title} className="border-zinc-200 bg-white">
                    <CardContent className="p-6">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-zinc-200 bg-zinc-50">
                        <Icon className="h-5 w-5 text-zinc-900" />
                      </div>
                      <h3 className="mt-5 text-lg font-semibold tracking-tight text-zinc-950">{item.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-zinc-600">{item.description}</p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </section>

        <section id="about" className="border-t border-zinc-200 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="grid gap-10 lg:grid-cols-[0.95fr_1.05fr]">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">About</p>
                <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                  Secure sharing without the usual tradeoff between convenience and control.
                </h2>
                <p className="mt-4 text-base leading-relaxed text-zinc-600">
                  HexShare is built for teams that need a better way to share sensitive documents with clients,
                  partners, and internal stakeholders while keeping the stack in their own control.
                </p>
              </div>

              <div className="grid gap-4">
                {aboutPoints.map((item) => (
                  <div key={item.title} className="rounded-xl border border-zinc-200 bg-zinc-50 p-6">
                    <h3 className="text-lg font-semibold tracking-tight text-zinc-950">{item.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-zinc-600">{item.description}</p>
                  </div>
                ))}
                <div className="rounded-xl border border-zinc-200 bg-white p-6">
                  <div className="flex items-start gap-3">
                    <Users className="mt-0.5 h-5 w-5 text-zinc-500" />
                    <div>
                      <h3 className="text-lg font-semibold tracking-tight text-zinc-950">Who it fits</h3>
                      <p className="mt-2 text-sm leading-relaxed text-zinc-600">
                        A strong fit for client delivery, internal review, and team workflows where access and visibility matter.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="faq" className="border-t border-zinc-200 bg-zinc-50 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">FAQ</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                Common questions.
              </h2>
            </div>

            <div className="mt-14 grid gap-4">
              {faqItems.map((item) => (
                <div key={item.question} className="rounded-xl border border-zinc-200 bg-white p-6">
                  <h3 className="text-lg font-semibold tracking-tight text-zinc-950">{item.question}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-zinc-600">{item.answer}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="contact" className="border-t border-zinc-200 px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="max-w-3xl">
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-zinc-500">Contact</p>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 sm:text-4xl">
                Deploy it or inspect the stack.
              </h2>
              <p className="mt-4 text-base leading-relaxed text-zinc-600">
                Start using HexShare, review the codebase, or use the repository as the entry point for self-hosting.
              </p>
            </div>

            <div className="mt-14 grid gap-6 md:grid-cols-3">
              <div className="rounded-xl border border-zinc-200 bg-white p-6">
                <Mail className="h-5 w-5 text-zinc-500" />
                <h3 className="mt-4 text-lg font-semibold tracking-tight text-zinc-950">Workspace access</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600">
                  Create a workspace or sign in through the configured identity flow for this deployment.
                </p>
                <div className="mt-5 flex flex-col gap-3">
                  <Link to="/signup">
                    <Button className="w-full justify-between">
                      Create workspace
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Link to="/login">
                    <Button variant="outline" className="w-full">
                      Sign in
                    </Button>
                  </Link>
                </div>
              </div>

              <div className="rounded-xl border border-zinc-200 bg-white p-6">
                <Github className="h-5 w-5 text-zinc-500" />
                <h3 className="mt-4 text-lg font-semibold tracking-tight text-zinc-950">Source and docs</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600">
                  Explore the repository, architecture notes, and self-hosting guides behind the product.
                </p>
                <a
                  href={repoUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-5 inline-flex w-full items-center justify-between rounded-md border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-50"
                >
                  Open repository
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>

              <div className="rounded-xl border border-zinc-200 bg-white p-6">
                <Clock3 className="h-5 w-5 text-zinc-500" />
                <h3 className="mt-4 text-lg font-semibold tracking-tight text-zinc-950">Technical discussion</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600">
                  Use the issue tracker for bugs, implementation questions, and deployment-related discussion.
                </p>
                <a
                  href={issuesUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-5 inline-flex w-full items-center justify-between rounded-md border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-50"
                >
                  Open issues
                  <ArrowRight className="h-4 w-4" />
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-zinc-200 bg-white px-6 py-8 lg:px-8">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 text-sm text-zinc-500 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <HexLogo className="h-6 w-6" />
            <span>HexShare</span>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <a href="#about" className="hover:text-zinc-900">About</a>
            <a href="#faq" className="hover:text-zinc-900">FAQ</a>
            <a href="#contact" className="hover:text-zinc-900">Contact</a>
            <a href={repoUrl} target="_blank" rel="noreferrer" className="hover:text-zinc-900">GitHub</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
