import { useState } from 'react';
import { ArrowRight, Lock } from 'lucide-react';
import { Button } from './ui/Button';
import type { AuthProvider } from '../services/api';

export function IdentityProviderButton({
  provider,
  isLoading,
  fallbackLabel,
  onClick,
}: {
  provider?: AuthProvider;
  isLoading: boolean;
  fallbackLabel: string;
  onClick: () => void;
}) {
  const [failedLogoUrl, setFailedLogoUrl] = useState<string | null>(null);
  const logoUrl = provider?.logo_url;
  const displayName = provider?.display_name?.trim();

  return (
    <Button
      type="button"
      variant="outline"
      className="h-auto min-h-14 w-full gap-3 rounded-xl px-4 py-3 text-zinc-900"
      disabled={isLoading}
      aria-busy={isLoading}
      onClick={onClick}
    >
      {logoUrl && logoUrl !== failedLogoUrl ? (
        <img
          src={logoUrl}
          alt=""
          width={24}
          height={24}
          className="h-6 w-6 shrink-0 object-contain"
          referrerPolicy="no-referrer"
          onError={() => setFailedLogoUrl(logoUrl)}
        />
      ) : (
        <Lock className="h-6 w-6 shrink-0 text-zinc-500" aria-hidden="true" />
      )}
      <span className="min-w-0 flex-1 break-words text-left">
        {isLoading ? 'Redirecting...' : displayName ? `Continue with ${displayName}` : fallbackLabel}
      </span>
      <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
    </Button>
  );
}
