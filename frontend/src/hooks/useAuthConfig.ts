import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { AuthConfig } from '../services/api';

export function useAuthConfig() {
  const [config, setConfig] = useState<AuthConfig | null>(null);

  useEffect(() => {
    let active = true;
    api.authConfig()
      .then((value) => {
        if (active) setConfig(value);
      })
      .catch(() => {
        // Authentication remains available with generic branding.
      });
    return () => {
      active = false;
    };
  }, []);

  return config;
}
