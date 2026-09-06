import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import Cookies from 'js-cookie';

export interface Actor {
  id: string;
  role: string;
  email?: string;
}

interface AuthState {
  actor: Actor | null;
  accessToken: string | null;
  refreshToken: string | null;
  setAuth: (actor: Actor, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      actor: null,
      accessToken: null,
      refreshToken: null,
      setAuth: (actor, accessToken, refreshToken) => {
        // Sync tokens to cookies for Next.js Middleware
        Cookies.set('accessToken', accessToken, { path: '/' });
        Cookies.set('refreshToken', refreshToken, { path: '/' });
        set({ actor, accessToken, refreshToken });
      },
      clearAuth: () => {
        Cookies.remove('accessToken', { path: '/' });
        Cookies.remove('refreshToken', { path: '/' });
        set({ actor: null, accessToken: null, refreshToken: null });
      },
    }),
    {
      name: 'auth-storage', // name of the item in the storage (must be unique)
      // by default, it uses localStorage
    }
  )
);
