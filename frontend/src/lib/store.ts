import { create } from 'zustand';

export interface Actor {
  id: string;
  role: string;
  email?: string;
}

interface AuthState {
  actor: Actor | null;
  isLoading: boolean;
  setActor: (actor: Actor | null) => void;
  setLoading: (isLoading: boolean) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  actor: null,
  isLoading: true,
  setActor: (actor) => set({ actor }),
  setLoading: (isLoading) => set({ isLoading }),
  clearAuth: () => set({ actor: null, isLoading: false }),
}));
