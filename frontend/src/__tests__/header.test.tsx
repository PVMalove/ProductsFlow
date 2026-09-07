import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Header } from '@/components/layout/header';
import { useAuthStore } from '@/lib/store';
import { authApi } from '@/lib/api/auth';

jest.mock('@/lib/api/auth', () => ({
  authApi: {
    logout: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
  }),
}));

describe('Header', () => {
  beforeEach(() => {
    useAuthStore.setState({ actor: null, isLoading: false });
    jest.clearAllMocks();
  });

  it('renders Guest links when not authenticated', () => {
    render(<Header />);
    expect(screen.getByText('Вход')).toBeInTheDocument();
    expect(screen.getByText('Регистрация')).toBeInTheDocument();
    expect(screen.queryByText('Мои товары')).not.toBeInTheDocument();
  });

  it('renders User links when authenticated as USER', () => {
    useAuthStore.setState({
      actor: { id: '1', role: 'user', email: 'user@example.com' },
    });
    render(<Header />);
    expect(screen.getByText('Мои товары')).toBeInTheDocument();
    expect(screen.getByText('Поиск')).toBeInTheDocument();
    expect(screen.getByText('Поддержка')).toBeInTheDocument();
    expect(screen.queryByText('Админка')).not.toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('Выйти')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Мои товары' })).toHaveAttribute(
      'href',
      '/owner/dashboard',
    );
    expect(screen.getByRole('link', { name: 'Поиск' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.getByRole('link', { name: 'Поддержка' })).toHaveAttribute(
      'href',
      '/support/tickets/new',
    );
  });

  it('renders Admin link when authenticated as ADMIN', () => {
    useAuthStore.setState({
      actor: { id: '2', role: 'admin', email: 'admin@example.com' },
    });
    render(<Header />);
    expect(screen.getByRole('link', { name: 'Админка' })).toHaveAttribute(
      'href',
      '/admin/audit-log',
    );
  });

  it('calls logout API and clears store on logout click', async () => {
    useAuthStore.setState({
      actor: { id: '1', role: 'user', email: 'user@example.com' },
    });
    
    (authApi.logout as jest.Mock).mockResolvedValueOnce(undefined);

    render(<Header />);
    const logoutBtn = screen.getByText('Выйти');
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(authApi.logout).toHaveBeenCalledTimes(1);
    });

    expect(useAuthStore.getState().actor).toBeNull();
  });
});
