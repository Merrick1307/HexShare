import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Building2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { HexLogo } from '../components/ui/HexLogo';
import { api } from '../services/api';

export function Signup({
  productName = 'HexShare',
  brandLogo,
}: {
  productName?: string;
  brandLogo?: React.ReactNode;
}) {
  const [isLoading, setIsLoading] = useState(false);

  function handleSSOSignup() {
    setIsLoading(true);
    window.location.href = api.signupUrl;
  }

  return (
    <div className="flex min-h-screen flex-col justify-center bg-zinc-50 px-4 py-8 sm:px-6 sm:py-12 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md flex flex-col items-center">
        <Link to="/" className="mb-6 flex items-center gap-3 text-zinc-950 sm:mb-8">
          {brandLogo ?? <HexLogo className="h-12 w-12" />}
          <span className="text-2xl font-semibold tracking-tight sm:text-3xl">{productName}</span>
        </Link>
      </div>

      <div className="w-full sm:mx-auto sm:max-w-md">
        <Card className="border-zinc-200 shadow-sm">
          <CardHeader className="space-y-1 text-center">
            <CardTitle className="text-2xl">Create a workspace</CardTitle>
            <CardDescription>
              Start an individual workspace for protected documents and ordered rooms.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-600">
              <div className="flex items-start gap-3">
                <Building2 className="mt-0.5 h-4 w-4 text-zinc-400" />
                <p>You will be redirected to the configured identity provider to continue.</p>
              </div>
            </div>
            <p className="text-center text-xs leading-relaxed text-zinc-500">
              Upload common business documents after signup. PDF provides the strongest
              recipient-watermarked viewer; other accepted formats show their protection
              level before sharing.
            </p>
            <Button type="button" className="w-full gap-2" disabled={isLoading} onClick={handleSSOSignup}>
              {isLoading ? 'Redirecting...' : 'Continue to signup'}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
