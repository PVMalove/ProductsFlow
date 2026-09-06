import { apiClient } from '../apiClient';
import { Actor } from '../store';
import { ApiResponse } from './types';

export interface RegisterRequest {
  email: string;
  password: string;
}

export const authApi = {
  async login(data: RegisterRequest) {
    const params = new URLSearchParams();
    params.append('username', data.email);
    params.append('password', data.password);
    
    const res = await apiClient.post('/v1/auth/login', params, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return res.data;
  },

  async register(data: RegisterRequest) {
    const res = await apiClient.post<ApiResponse<Actor>>('/v1/auth/register', data);
    return res.data;
  },

  async getMe() {
    const res = await apiClient.get<Actor>('/v1/users/me');
    return res.data;
  },
  
  async logout() {
    const res = await apiClient.post('/v1/auth/logout');
    return res.data;
  }
};
