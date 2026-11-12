import axios from 'axios';
import type { LoginResponse, User } from '../types';

const TOKEN_KEY = 'mds.token';

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 10000,
});

api.interceptors.request.use((cfg) => {
  const t = tokenStorage.get();
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export async function loginRequest(email: string, password: string): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/api/auth/login', { email, password });
  return data;
}

export async function meRequest(): Promise<User> {
  const { data } = await api.get<User>('/api/auth/me');
  return data;
}

export async function logoutRequest(): Promise<void> {
  await api.post('/api/auth/logout');
}
