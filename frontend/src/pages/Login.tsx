import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Lock, Sparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { HexLogo } from '../components/ui/HexLogo';
import { api } from '../services/api';

export function Login({
  productName = 'HexShare',
  brandLogo,
}: {
  productName?: string;
  brandLogo?: React.ReactNode;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    api
      .authConfig()
      .then((config) => {
        if (active) setDemoMode(Boolean(config.demo_mode));
      })
      .catch(() => {
        if (active) setDemoMode(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function handleSSOLogin() {
    setIsLoading(true);
    window.location.href = api.loginUrl;
  }

  async function handleDemoLogin() {
    setDemoLoading(true);
    setDemoError(null);
    try {
      await api.demoLogin();
      navigate('/dashboard');
    } catch (err) {
      setDemoError(err instanceof Error ? err.message : 'Demo login failed.');
      setDemoLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col justify-center bg-zinc-50 py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md flex flex-col items-center">
        <Link to="/" className="mb-8 flex items-center gap-3 text-zinc-950">
          {brandLogo ?? <HexLogo className="h-12 w-12" />}
          <span className="text-3xl font-semibold tracking-tight">{productName}</span>
        </Link>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-1 text-center">
            <CardTitle className="text-2xl">Sign in to {productName}</CardTitle>
            <CardDescription>Continue with the configured single sign-on provider for this workspace.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {demoMode && (
              <div className="space-y-2">
                <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900">
                  <div className="flex items-start gap-3">
                    <Sparkles className="mt-0.5 h-4 w-4 text-indigo-500" />
                    <p>This is a public demo. Jump straight into a populated workspace — no account needed.</p>
                  </div>
                </div>
                <Button
                  type="button"
                  className="w-full gap-2"
                  disabled={demoLoading}
                  onClick={handleDemoLogin}
                >
                  {demoLoading ? 'Loading demo...' : 'Try the demo'}
                  <ArrowRight className="h-4 w-4" />
                </Button>
                {demoError && <p className="text-center text-sm text-red-600">{demoError}</p>}
                <div className="flex items-center gap-3 py-1">
                  <span className="h-px flex-1 bg-zinc-200" />
                  <span className="text-xs uppercase tracking-wide text-zinc-400">or</span>
                  <span className="h-px flex-1 bg-zinc-200" />
                </div>
              </div>
            )}
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
              <div className="flex items-start gap-3">
                <Lock className="mt-0.5 h-4 w-4 text-zinc-400" />
                <p>Authenticate with your configured identity provider.</p>
              </div>
            </div>
            <Button
              type="button"
              variant={demoMode ? 'outline' : 'primary'}
              className="w-full gap-2"
              disabled={isLoading}
              onClick={handleSSOLogin}
            >
              {isLoading ? 'Redirecting...' : 'Continue to sign in'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
