'use client';

import { useEffect, type ReactNode } from 'react';
import { authApi } from '@/lib/api/auth';
import { clearAccessToken, getAccessToken } from '@/lib/auth-token';
import { useAuthStore, type Actor } from '@/lib/store';

let pendingActorRequest: Promise<Actor> | null = null;

function getCurrentActor(): Promise<Actor> {
  pendingActorRequest ??= authApi.getMe().finally(() => {
    pendingActorRequest = null;
  });
  return pendingActorRequest;
}

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  const { actor, setActor, clearAuth } = useAuthStore();

  useEffect(() => {
    if (actor) return;

    if (!getAccessToken()) {
      // The initial loading state is resolved here after client hydration.
      clearAuth();
      return;
    }

    let active = true;
    void getCurrentActor()
      .then((currentActor) => {
        if (active) setActor(currentActor);
      })
      .catch(() => {
        if (!active) return;
        clearAccessToken();
        clearAuth();
      });

    return () => {
      active = false;
    };
  }, [actor, clearAuth, setActor]);

  return children;
}
