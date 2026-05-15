import React from 'react';
import { Link } from 'react-router-dom';
import { Shield, Zap, Eye, ArrowRight, Lock } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { HexLogo } from '../components/ui/HexLogo';

export function Landing() {
  return (
    <div className="min-h-screen bg-white text-zinc-950 flex flex-col">
      {/* Navigation */}
      <header className="h-20 border-b border-zinc-100 flex items-center justify-between px-6 lg:px-12">
        <div className="flex items-center gap-3">
          <HexLogo className="h-9 w-9" />
          <span className="font-semibold tracking-tight text-xl">HexShare</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/login" className="text-sm font-medium text-zinc-600 hover:text-zinc-900 transition-colors">
            Sign In
          </Link>
          <Link to="/signup">
            <Button size="sm">Get Started</Button>
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col">
        <section className="px-6 py-24 lg:px-12 lg:py-32 max-w-5xl mx-auto text-center flex flex-col items-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold tracking-wide uppercase mb-8 border border-indigo-100">
            <Lock className="h-3 w-3" />
            Enterprise-Grade Security
          </div>
          <h1 className="text-5xl lg:text-7xl font-semibold tracking-tight text-zinc-950 mb-6 leading-[1.1]">
            Secure document sharing <br className="hidden lg:block" />
            <span className="text-zinc-500">for modern teams.</span>
          </h1>
          <p className="text-lg text-zinc-500 max-w-2xl mb-10 leading-relaxed">
            Share sensitive documents with confidence. HexShare provides fine-grained permissions, instant revocation, and comprehensive audit logging powered by HexIAM.
          </p>
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <Link to="/signup">
              <Button size="lg" className="gap-2 w-full sm:w-auto">
                Start for free <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/login">
              <Button size="lg" variant="outline" className="w-full sm:w-auto">
                Sign in to workspace
              </Button>
            </Link>
          </div>
        </section>

        {/* Features Grid */}
        <section className="bg-zinc-50 border-t border-zinc-100 py-24 px-6 lg:px-12 flex-1">
          <div className="max-w-6xl mx-auto">
            <div className="grid md:grid-cols-3 gap-12">
              <div className="space-y-4">
                <div className="h-12 w-12 rounded-xl bg-white border border-zinc-200 flex items-center justify-center shadow-sm">
                  <Shield className="h-6 w-6 text-zinc-900" />
                </div>
                <h3 className="text-xl font-semibold tracking-tight">Granular Control</h3>
                <p className="text-zinc-500 leading-relaxed">
                  Set expiration dates, disable downloads, prevent printing, and restrict access to specific email addresses.
                </p>
              </div>
              <div className="space-y-4">
                <div className="h-12 w-12 rounded-xl bg-white border border-zinc-200 flex items-center justify-center shadow-sm">
                  <Zap className="h-6 w-6 text-zinc-900" />
                </div>
                <h3 className="text-xl font-semibold tracking-tight">Instant Revocation</h3>
                <p className="text-zinc-500 leading-relaxed">
                  Kill access to any document instantly. Once revoked, active sessions are terminated and links become permanently invalid.
                </p>
              </div>
              <div className="space-y-4">
                <div className="h-12 w-12 rounded-xl bg-white border border-zinc-200 flex items-center justify-center shadow-sm">
                  <Eye className="h-6 w-6 text-zinc-900" />
                </div>
                <h3 className="text-xl font-semibold tracking-tight">Audit & Analytics</h3>
                <p className="text-zinc-500 leading-relaxed">
                  Track exactly who viewed your documents, when, and for how long. Export audit logs for compliance requirements.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
