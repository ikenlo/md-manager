import { LogOut, Moon, Sun } from 'lucide-react';
import { Avatar, Button, Card, CardHead, Chip, Seg, Topbar } from '../components/ui';
import { PageContainer } from '../layout/AppShell';
import { ROLE_LABEL } from '../lib/nav';
import { logout } from '../lib/session';
import { setTheme, useTheme, type Theme } from '../lib/theme';
import { useAuthStore } from '../store/auth';

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const isMock = useAuthStore((s) => s.isMock);
  const theme = useTheme();
  const name = user?.display_name || 'Адміністратор';

  return (
    <PageContainer>
      <Topbar title="Налаштування" sub="Профіль, вигляд і сесія" />
      <div className="grid grid-cols-1 gap-3 min-[1100px]:grid-cols-2">
        <Card>
          <CardHead title="Профіль" />
          <div className="flex items-center gap-3 rounded-md border border-line bg-surface-2 p-3">
            <Avatar name={name} size="lg" />
            <div className="min-w-0 flex-1">
              <b className="block truncate text-[15px] text-ink">{name}</b>
              <span className="block truncate text-[13px] text-ink-3">{user?.email}</span>
            </div>
            <Chip variant="ok">{ROLE_LABEL[user?.role ?? ''] ?? user?.role}</Chip>
          </div>
          {isMock && <p className="mt-3 text-xs text-ink-3">Демо-вхід без сервера: дані вбудовані, нічого не зберігається.</p>}
        </Card>

        <Card>
          <CardHead title="Вигляд" />
          <p className="mb-3 text-[13px] text-ink-2">Тема застосовується одразу й запам'ятовується на цьому пристрої.</p>
          <Seg<Theme>
            aria-label="Тема"
            value={theme}
            onChange={setTheme}
            options={[
              { value: 'light', label: 'Світла', icon: <Sun size={14} aria-hidden="true" /> },
              { value: 'dark', label: 'Темна', icon: <Moon size={14} aria-hidden="true" /> },
            ]}
          />
        </Card>

        <Card>
          <CardHead title="AI-адміністратор" />
          <ul className="flex flex-col gap-2 text-[13px] text-ink-2">
            <li>
              <b className="text-ink">AI авто</b> — пропозиція готується сама на кожне нове повідомлення.
            </li>
            <li>
              <b className="text-ink">Вручну</b> — кнопка «Запустити AI» в чаті.
            </li>
            <li>
              <b className="text-ink">Людина</b> — AI вимкнено для діалогу.
            </li>
            <li className="text-ink-3">Режим задається в шапці кожного діалогу. Без вашого «Схвалити» клієнт нічого не отримає.</li>
          </ul>
        </Card>

        <Card>
          <CardHead title="Сесія" />
          <p className="mb-3 text-[13px] text-ink-2">Автовихід після 30 хвилин без дій.</p>
          <Button variant="danger" iconLeft={<LogOut size={16} />} onClick={logout}>
            Вийти
          </Button>
        </Card>
      </div>
    </PageContainer>
  );
}
