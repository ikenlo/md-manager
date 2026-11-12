import axios from 'axios';
import { create } from 'zustand';
import { loginRequest, logoutRequest, tokenStorage } from '../api/client';
import type { User } from '../types';

const USER_KEY = 'mds.user';
const MOCK_TOKEN = 'mock-token';

// Демо-вхід, коли бекенд не запущено (Фаза 1)
const MOCK_USER: User = {
  uuid: 'mock-admin',
  email: 'admin@mds.local',
  display_name: 'Директор',
  role: 'director',
};

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

interface AuthState {
  token: string | null;
  user: User | null;
  isMock: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set, get) => ({
  token: tokenStorage.get(),
  user: loadUser(),
  isMock: tokenStorage.get() === MOCK_TOKEN,

  async login(email, password) {
    try {
      const res = await loginRequest(email, password);
      tokenStorage.set(res.token);
      localStorage.setItem(USER_KEY, JSON.stringify(res.user));
      set({ token: res.token, user: res.user, isMock: false });
    } catch (err) {
      const offline = axios.isAxiosError(err) && (!err.response || err.response.status >= 500);
      if (offline && email.trim().toLowerCase() === MOCK_USER.email && password === 'admin') {
        tokenStorage.set(MOCK_TOKEN);
        localStorage.setItem(USER_KEY, JSON.stringify(MOCK_USER));
        set({ token: MOCK_TOKEN, user: MOCK_USER, isMock: true });
        return;
      }
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        throw new Error('Невірний email або пароль');
      }
      if (offline) throw new Error('Сервер недоступний. Спробуйте пізніше');
      throw new Error('Не вдалося увійти');
    }
  },

  logout() {
    if (!get().isMock) logoutRequest().catch(() => undefined);
    tokenStorage.clear();
    localStorage.removeItem(USER_KEY);
    set({ token: null, user: null, isMock: false });
  },
}));
