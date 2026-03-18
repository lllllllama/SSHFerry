import { create } from 'zustand';

import type { AuthSessionResponse, HealthResponse } from '../api/types';

type AuthStatus = 'idle' | 'loading' | 'ready' | 'error';

interface AuthState {
  status: AuthStatus;
  token: string | null;
  headerName: string;
  health: HealthResponse | null;
  initError: string | null;
  setLoading: () => void;
  setBackendSession: (payload: { health: HealthResponse; session: AuthSessionResponse }) => void;
  setInitError: (message: string) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'idle',
  token: null,
  headerName: 'X-SSHFerry-Token',
  health: null,
  initError: null,
  setLoading: () => set((state) => (state.status === 'ready' ? state : { status: 'loading', initError: null })),
  setBackendSession: ({ health, session }) =>
    set({
      status: 'ready',
      token: session.token,
      headerName: session.header_name || health.auth_header_name || 'X-SSHFerry-Token',
      health,
      initError: null,
    }),
  setInitError: (message) =>
    set((state) => ({
      status: 'error',
      token: state.token,
      headerName: state.headerName,
      health: state.health,
      initError: message,
    })),
  reset: () =>
    set({
      status: 'idle',
      token: null,
      headerName: 'X-SSHFerry-Token',
      health: null,
      initError: null,
    }),
}));
