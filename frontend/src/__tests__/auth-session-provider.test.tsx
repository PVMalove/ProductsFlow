import { render, screen, waitFor } from '@testing-library/react';
import Cookies from 'js-cookie';
import { Header } from '@/components/layout/header';
import { authApi } from '@/lib/api/auth';
import { useAuthStore } from '@/lib/store';
import { AuthSessionProvider } from '@/providers/auth-session-provider';

jest.mock('@/lib/api/auth', () => ({
  authApi: {
    getMe: jest.fn(),
    logout: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

describe('AuthSessionProvider', () => {
  beforeEach(() => {
    Cookies.remove('accessToken', { path: '/' });
    useAuthStore.setState({ actor: null, isLoading: true });
    jest.clearAllMocks();
  });

  it('finishes session loading without requesting a profile when no token exists', async () => {
    render(
      <AuthSessionProvider>
        <Header />
      </AuthSessionProvider>,
    );

    expect(await screen.findByText('Вход')).toBeInTheDocument();
    expect(authApi.getMe).not.toHaveBeenCalled();
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('restores the actor from an existing session after the app remounts', async () => {
    Cookies.set('accessToken', 'persisted-access-token', { path: '/' });
    jest.mocked(authApi.getMe).mockResolvedValue({
      id: 'user-1',
      role: 'user',
      email: 'user@example.com',
    });

    render(
      <AuthSessionProvider>
        <Header />
      </AuthSessionProvider>,
    );

    expect(await screen.findByText('user@example.com')).toBeInTheDocument();
    await waitFor(() => {
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
    expect(authApi.getMe).toHaveBeenCalledTimes(1);
  });
});
