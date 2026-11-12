import { Loader2, Lock, Mail } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../store/auth';

export default function LoginPage() {
  const { token, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('admin@mds.local');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (token) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не вдалося увійти');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-brand px-4 py-10">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(180,138,62,.18),transparent_45%),radial-gradient(circle_at_85%_90%,rgba(29,77,59,.9),transparent_50%)]" />
      <form onSubmit={submit} className="relative w-full max-w-[400px] rounded-3xl bg-surface p-9 shadow-card">
        <div className="text-center">
          <div className="font-serif text-5xl font-bold leading-none text-gold">M&amp;D</div>
          <div className="mt-2 text-[11px] font-bold uppercase tracking-[0.3em] text-ink-3">MDs Manager</div>
          <h1 className="mt-6 font-serif text-[28px] font-bold text-brand">Вхід до системи</h1>
          <p className="mt-1 text-sm text-ink-2">AI-адміністратор салону</p>
        </div>

        <label className="mt-8 block text-xs font-semibold text-ink-2">
          Email
          <span className="mt-1.5 flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-3 focus-within:border-gold">
            <Mail size={16} className="text-ink-3" />
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-transparent text-sm text-ink outline-none"
            />
          </span>
        </label>
        <label className="mt-4 block text-xs font-semibold text-ink-2">
          Пароль
          <span className="mt-1.5 flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-3 focus-within:border-gold">
            <Lock size={16} className="text-ink-3" />
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-transparent text-sm text-ink outline-none"
            />
          </span>
        </label>

        {error && (
          <p role="alert" className="mt-4 rounded-xl bg-[#f9e9e6] px-3 py-2 text-sm text-[#9b3b2c]">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-brand py-3 text-sm font-bold text-brand-ink transition hover:bg-brand-2 disabled:opacity-60"
        >
          {busy && <Loader2 size={16} className="animate-spin" />}
          Увійти
        </button>
        <p className="mt-5 text-center text-xs text-ink-3">Салон краси M&amp;D · Київ</p>
      </form>
    </div>
  );
}
