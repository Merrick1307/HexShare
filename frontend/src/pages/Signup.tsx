import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { HexLogo } from '../components/ui/HexLogo';
import { api } from '../services/api';
import { IdentityProviderButton } from '../components/IdentityProviderButton';
import { useAuthConfig } from '../hooks/useAuthConfig';

export function Signup({
  productName = 'HexShare',
  brandLogo,
}: {
  productName?: string;
  brandLogo?: React.ReactNode;
}) {
  const [isLoading, setIsLoading] = useState(false);
  const authConfig = useAuthConfig();

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
            <IdentityProviderButton
              provider={authConfig?.provider}
              isLoading={isLoading}
              fallbackLabel="Continue to signup"
              onClick={handleSSOSignup}
            />
            <p className="text-center text-xs leading-relaxed text-zinc-500">
              Upload common business documents after signup. PDF provides the strongest
              recipient-watermarked viewer; other accepted formats show their protection
              level before sharing.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
