import axios from 'axios';
import { AlertCircle, ArrowRight, Lock, User } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { loginRequest } from '../api/client';
import { Button, Input } from '../components/ui';
import { parseExpiry, selectIsAuthenticated, useAuthStore } from '../store/auth';
import type { User as AppUser } from '../types';

const LAST_LOGIN_KEY = 'mds_last_login';
const LOGIN_DOMAIN = '@mds.local';

// Демо-вхід без бекенда — лише в `npm run dev`, у зібраній версії гілка вирізається
const MOCK_USER: AppUser = { uuid: 'mock-admin', email: 'admin@mds.local', display_name: 'Директор', role: 'director' };

/** «admin» → «admin@mds.local»; email лишається як є. */
const toEmail = (identifier: string) => {
  const v = identifier.trim().toLowerCase();
  return v.includes('@') ? v : `${v}${LOGIN_DOMAIN}`;
};

const readLast = () => {
  try {
    return localStorage.getItem(LAST_LOGIN_KEY) ?? '';
  } catch {
    return '';
  }
};

function minutesLabel(sec: number) {
  const m = Math.floor(sec / 60);
  const s = String(sec % 60).padStart(2, '0');
  return `${m}:${s}`;
}

export default function LoginPage() {
  const authed = useAuthStore(selectIsAuthenticated);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;

  const [identifier, setIdentifier] = useState(readLast);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lockedFor, setLockedFor] = useState(0); // секунд до зняття ліміту 429
  const passRef = useRef<HTMLInputElement>(null);
  const idRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (identifier ? passRef : idRef).current?.focus();
    // лише при першому показі
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (lockedFor <= 0) return;
    const t = setTimeout(() => setLockedFor((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [lockedFor]);

  if (authed) return <Navigate to={from && from !== '/login' ? from : '/'} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || lockedFor > 0) return;
    if (!identifier.trim() || !password) {
      setError('Введіть логін і пароль');
      return;
    }
    setError(null);
    setBusy(true);
    const email = toEmail(identifier);
    try {
      const res = await loginRequest(email, password);
      try {
        localStorage.setItem(LAST_LOGIN_KEY, identifier.trim());
      } catch {
        /* ignore */
      }
      setAuth(res.token, res.user, parseExpiry(res.expires_at));
      navigate(from && from !== '/login' ? from : '/', { replace: true });
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const offline = axios.isAxiosError(err) && (!err.response || err.response.status >= 500);
      if (import.meta.env.DEV && offline && email === MOCK_USER.email && password === 'admin') {
        setAuth('mock-token', MOCK_USER, Date.now() + 7 * 86_400_000, true);
        navigate('/', { replace: true });
        return;
      }
      if (status === 401) setError('Невірний логін або пароль');
      else if (status === 429) {
        const header = axios.isAxiosError(err) ? Number(err.response?.headers?.['retry-after']) : NaN;
        setLockedFor(Number.isFinite(header) && header > 0 ? Math.ceil(header) : 15 * 60);
        setError(null);
      } else if (status === 422) setError('Перевірте формат логіна');
      else if (offline) setError('Сервер недоступний. Спробуйте пізніше');
      else setError('Не вдалося увійти');
      setPassword('');
      passRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const message =
    lockedFor > 0 ? `Забагато спроб. Спробуйте через 15 хвилин (залишилось ${minutesLabel(lockedFor)}).` : error;

  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden bg-bg px-4 py-10 sm:px-6">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_480px_at_85%_-10%,rgba(180,138,62,.14),transparent_60%),radial-gradient(700px_420px_at_0%_110%,rgba(20,57,44,.10),transparent_60%)]"
      />
      <main className="relative w-full max-w-[400px]">
        <div className="relative overflow-hidden rounded-xl border border-line bg-surface px-6 pb-7 pt-9 shadow-lg sm:px-8">
          <div aria-hidden="true" className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-brand via-gold to-brand" />

          <div className="text-center">
            <div
              aria-hidden="true"
              className="mx-auto mb-4 grid h-[66px] w-[66px] place-items-center rounded-xl bg-gradient-to-br from-[#d8b46a] to-[#a9823b] font-serif text-[22px] font-semibold text-[#1a1408] shadow-[0_0_0_6px_theme(colors.gold.tint),0_10px_28px_rgba(180,138,62,.3)]"
            >
              M&amp;D
            </div>
            <h1 className="font-serif text-[34px] font-semibold leading-none text-brand">M&amp;D</h1>
            <div className="mt-2 text-2xs font-semibold uppercase tracking-[0.24em] text-ink-3">MDs Manager</div>
            <p className="mt-5 text-sm text-ink-2">Увійдіть у систему</p>
          </div>

          <form onSubmit={submit} noValidate className="mt-6 flex flex-col gap-4">
            <Input
              ref={idRef}
              label="Логін або Email"
              name="identifier"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="admin"
              iconLeft={<User size={16} />}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
            />
            <Input
              ref={passRef}
              label="Пароль"
              name="password"
              type="password"
              autoComplete="current-password"
              iconLeft={<Lock size={16} />}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />

            {message && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-sm text-danger"
              >
                <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
                <span>{message}</span>
              </div>
            )}

            <Button
              type="submit"
              size="lg"
              fullWidth
              loading={busy}
              disabled={lockedFor > 0}
              iconRight={<ArrowRight size={16} />}
              className="mt-1"
            >
              Увійти
            </Button>
          </form>
        </div>
        <p className="mt-5 flex items-center justify-center gap-1.5 text-center text-xs text-ink-3">
          <Lock size={12} aria-hidden="true" />
          Салон краси M&amp;D · доступ лише для персоналу
        </p>
      </main>
    </div>
  );
}
