import axios from 'axios';
import { AlertCircle, ArrowRight, Eye, EyeOff, Lock, User } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { loginRequest } from '../api/client';
import { Button, Input, cn } from '../components/ui';
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
  const [showPass, setShowPass] = useState(false);
  const [caps, setCaps] = useState(false);
  const [shake, setShake] = useState(0); // лічильник: кожна помилка — новий «струс» картки
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
      setShake((n) => n + 1);
      passRef.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const message =
    lockedFor > 0 ? `Забагато спроб. Спробуйте через 15 хвилин (залишилось ${minutesLabel(lockedFor)}).` : error;

  const labelCls = '[&_label]:text-xs [&_label]:font-semibold [&_label]:uppercase [&_label]:tracking-[.06em] [&_label]:text-ink-3';

  return (
    <div className="relative flex min-h-full flex-col items-center justify-center gap-[18px] overflow-hidden bg-bg bg-[radial-gradient(900px_480px_at_85%_-10%,rgba(180,138,62,.14),transparent_60%),radial-gradient(700px_420px_at_0%_110%,rgba(20,57,44,.10),transparent_60%)] px-4 py-6 pb-[calc(24px+env(safe-area-inset-bottom))] dark:bg-[radial-gradient(900px_480px_at_85%_-10%,rgba(210,171,95,.12),transparent_60%),radial-gradient(700px_420px_at_0%_110%,rgba(20,57,44,.35),transparent_60%)]">
      <main className="relative w-full max-w-[400px]">
        <div
          key={shake}
          className={cn(
            'relative overflow-hidden rounded-xl border border-line bg-surface px-7 pb-[26px] pt-[34px] text-center shadow-lg max-[380px]:px-[18px]',
            shake ? 'animate-shake' : 'animate-rise-in',
          )}
        >
          <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-brand via-gold to-brand" />

          <div
            aria-hidden="true"
            className="mx-auto mb-3.5 grid h-[66px] w-[66px] animate-mark-in place-items-center rounded-xl bg-gradient-to-br from-[#d8b46a] to-[#a9823b] font-serif text-[22px] font-semibold text-[#1a1408] shadow-[0_0_0_6px_rgb(var(--gold-tint)),0_10px_28px_rgba(180,138,62,.3)]"
          >
            M&amp;D
          </div>
          <h1 className="font-serif text-[30px] font-semibold leading-[1.1] text-brand dark:text-gold">MDs Manager</h1>
          <div className="mb-6 mt-1.5 text-2xs font-semibold uppercase tracking-[0.2em] text-ink-3">Салон M&amp;D · AI-адміністратор</div>

          <form onSubmit={submit} noValidate className={cn('flex flex-col gap-3 text-left', labelCls)}>
            <Input
              ref={idRef}
              label="Логін"
              name="identifier"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="Ваш логін MDS Connect"
              iconLeft={<User size={16} />}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              inputClassName="min-h-12"
              required
            />
            <Input
              ref={passRef}
              label="Пароль"
              name="password"
              type={showPass ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="••••••••"
              iconLeft={<Lock size={16} />}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyUp={(e) => setCaps(e.getModifierState?.('CapsLock') ?? false)}
              inputClassName="min-h-12"
              trailing={
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  aria-label={showPass ? 'Сховати пароль' : 'Показати пароль'}
                  aria-pressed={showPass}
                  className="grid h-9 w-9 place-items-center rounded-sm text-ink-3 transition duration-1 hover:bg-surface-3 hover:text-brand-2 focus-visible:outline-none focus-visible:shadow-ring"
                >
                  {showPass ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              }
              required
            />

            {caps && (
              <div className="flex items-center gap-1.5 text-[13px] font-semibold text-warn">
                <AlertCircle size={14} aria-hidden="true" />
                Увімкнено Caps Lock
              </div>
            )}

            {message && (
              <div
                role="alert"
                className="flex animate-rise-in items-start gap-2 rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-[13px] text-danger"
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
              className="mt-1.5"
            >
              Увійти
            </Button>
          </form>
        </div>
      </main>
      <p className="flex flex-col items-center gap-1 text-center text-xs text-ink-3">
        <Lock size={14} aria-hidden="true" />
        Вхід тим самим логіном, що й у MDS Connect
      </p>
    </div>
  );
}
