import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Cookies from 'js-cookie';

import LoginPage from '@/app/login/page';
import RegisterPage from '@/app/register/page';
import { useAuthStore } from '@/lib/store';

const mockPush = jest.fn();

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('authentication pages', () => {
  beforeEach(() => {
    mockPush.mockClear();
    Cookies.remove('accessToken');
    useAuthStore.setState({ actor: null, isLoading: false });
  });

  it('logs in through the master bearer-token contract and loads the actor', async () => {
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password-123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));

    await waitFor(() => {
      expect(useAuthStore.getState().actor).toEqual({
        id: 'user-123',
        role: 'user',
        email: 'user@example.com',
      });
    });
    expect(Cookies.get('accessToken')).toBe('mock-access-token');
    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('registers through the canonical auth route', async () => {
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'new-user@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'password-123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Register' }));

    expect(
      await screen.findByText('Registration successful! Redirecting to login...'),
    ).toBeInTheDocument();
  });
});
