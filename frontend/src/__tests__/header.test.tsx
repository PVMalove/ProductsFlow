import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Header } from '@/components/layout/header';
import { useAuthStore } from '@/lib/store';
import { authApi } from '@/lib/api/auth';

const mockPush = jest.fn();
let mockPathname = '/';

jest.mock('@/lib/api/auth', () => ({
  authApi: {
    login: jest.fn(),
    getMe: jest.fn(),
    logout: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
  usePathname: () => mockPathname,
}));

describe('Header', () => {
  beforeEach(() => {
    useAuthStore.setState({ actor: null, isLoading: false });
    jest.clearAllMocks();
    mockPush.mockClear();
    mockPathname = '/';
  });

  it('renders Guest links when not authenticated', () => {
    render(<Header />);
    expect(screen.getByText('Вход')).toBeInTheDocument();
    expect(screen.getByText('Регистрация')).toBeInTheDocument();
    expect(screen.queryByText('Мои товары')).not.toBeInTheDocument();
  });

  it('opens an authorization dialog for a guest', () => {
    render(<Header />);

    fireEvent.click(screen.getByRole('button', { name: 'Вход' }));

    expect(screen.getByRole('dialog', { name: 'Вход' })).toBeInTheDocument();
  });

  it('keeps the login-page link for guests away from the home page', () => {
    mockPathname = '/catalog';
    render(<Header />);

    expect(screen.getByRole('link', { name: 'Вход' })).toHaveAttribute('href', '/login');
  });

  it('updates the header after a guest signs in without navigating away', async () => {
    jest.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-token',
      token_type: 'bearer',
    });
    jest.mocked(authApi.getMe).mockResolvedValue({
      id: 'user-1',
      role: 'user',
      email: 'user@example.com',
    });
    render(<Header />);

    fireEvent.click(screen.getByRole('button', { name: 'Вход' }));
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText('Пароль'), {
      target: { value: 'password-123' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }));

    expect(await screen.findByText('user@example.com')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Вход' })).not.toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
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
