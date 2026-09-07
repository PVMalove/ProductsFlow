import Cookies from 'js-cookie';

import { apiClient } from '@/lib/apiClient';
import { authApi } from '@/lib/api/auth';

jest.mock('js-cookie', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    remove: jest.fn(),
    set: jest.fn(),
  },
}));

jest.mock('@/lib/apiClient', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

const mockedPost = apiClient.post as jest.Mock;
const mockedGet = apiClient.get as jest.Mock;

describe('authApi routes', () => {
  beforeEach(() => {
    mockedPost.mockReset();
    mockedPost.mockResolvedValue({ data: {} });
    mockedGet.mockReset();
    jest.mocked(Cookies.remove).mockReset();
    jest.mocked(Cookies.set).mockReset();
  });

  it('posts login form to the auth route below the /api/v1 client base', async () => {
    mockedPost.mockResolvedValue({
      data: { access_token: 'access-token', token_type: 'bearer' },
    });

    await authApi.login({ email: 'user@example.com', password: 'password-123' });

    expect(mockedPost).toHaveBeenCalledWith(
      '/auth/login',
      expect.any(URLSearchParams),
      expect.objectContaining({
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }),
    );
    expect(Cookies.set).toHaveBeenCalledWith(
      'accessToken',
      'access-token',
      expect.objectContaining({ path: '/', sameSite: 'strict' }),
    );
  });

  it('posts registration data to the auth route below the /api/v1 client base', async () => {
    const payload = { email: 'user@example.com', password: 'password-123' };

    await authApi.register(payload);

    expect(mockedPost).toHaveBeenCalledWith('/auth/register', payload);
  });

  it('unwraps the BFF response returned by /users/me', async () => {
    const actor = { id: 'user-1', role: 'user', email: 'user@example.com' };
    mockedGet.mockResolvedValue({ data: { data: actor, meta: {} } });

    await expect(authApi.getMe()).resolves.toEqual(actor);
    expect(mockedGet).toHaveBeenCalledWith('/users/me');
  });

  it('logs out locally because master has no logout endpoint', async () => {
    await authApi.logout();

    expect(Cookies.remove).toHaveBeenCalledWith('accessToken', { path: '/' });
    expect(mockedPost).not.toHaveBeenCalled();
  });
});
