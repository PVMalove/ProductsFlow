import axios from 'axios';
import { useAuthStore } from './store';

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const store = useAuthStore.getState();
      // Only clear and redirect if we actually had an actor
      // to avoid redirect loops on public pages that might 401
      if (store.actor) {
        store.clearAuth();
        if (typeof window !== 'undefined') {
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);
