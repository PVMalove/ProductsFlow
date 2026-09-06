import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Header } from '@/components/layout/header';
import { useAuthStore } from '@/lib/store';
import { apiClient } from '@/lib/apiClient';

jest.mock('@/lib/apiClient', () => ({
  apiClient: {
    post: jest.fn(),
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
      actor: { id: '1', role: 'USER', email: 'user@example.com' },
    });
    render(<Header />);
    expect(screen.getByText('Мои товары')).toBeInTheDocument();
    expect(screen.getByText('Поиск')).toBeInTheDocument();
    expect(screen.getByText('Поддержка')).toBeInTheDocument();
    expect(screen.queryByText('Админка')).not.toBeInTheDocument();
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('Выйти')).toBeInTheDocument();
  });

  it('renders Admin link when authenticated as ADMIN', () => {
    useAuthStore.setState({
      actor: { id: '2', role: 'ADMIN', email: 'admin@example.com' },
    });
    render(<Header />);
    expect(screen.getByText('Админка')).toBeInTheDocument();
  });

  it('calls logout API and clears store on logout click', async () => {
    useAuthStore.setState({
      actor: { id: '1', role: 'USER', email: 'user@example.com' },
    });
    
    (apiClient.post as jest.Mock).mockResolvedValueOnce({});

    render(<Header />);
    const logoutBtn = screen.getByText('Выйти');
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith('/auth/logout');
    });

    expect(useAuthStore.getState().actor).toBeNull();
  });
});
