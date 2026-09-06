import { apiClient } from '../apiClient';
import { clearAccessToken, setAccessToken } from '../auth-token';
import type { Actor } from '../store';
import type { ApiResponse } from './types';

export interface RegisterRequest {
  email: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
}

export const authApi = {
  async login(data: RegisterRequest) {
    const params = new URLSearchParams();
    params.append('username', data.email);
    params.append('password', data.password);
    
    const res = await apiClient.post<TokenResponse>('/auth/login', params, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    setAccessToken(res.data.access_token);
    return res.data;
  },

  async register(data: RegisterRequest) {
    const res = await apiClient.post<ApiResponse<Actor>>('/auth/register', data);
    return res.data;
  },

  async getMe() {
    const res = await apiClient.get<ApiResponse<Actor>>('/users/me');
    return res.data.data;
  },
  
  async logout() {
    clearAccessToken();
  },
};
