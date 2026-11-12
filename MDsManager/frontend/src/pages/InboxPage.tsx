import { WifiOff } from 'lucide-react';
import { lazy, Suspense, useEffect, useState } from 'react';
import ActiveChat from '../components/ActiveChat';
import ChatList from '../components/ChatList';
import Sidebar from '../components/Sidebar';
import { cn, toast } from '../components/ui';
import { mockDialogues, mockMessages } from '../data/mock';
import { connect, disconnect } from '../lib/ws';
import { useAIStore } from '../store/ai';
import { useAuthStore } from '../store/auth';
import { useInboxStore } from '../store/inbox';

// Лише для `npm run dev`: у production-збірку не потрапляє
const BULK_PENDING_LIMIT = 20;

const DevPanel = import.meta.env.DEV ? lazy(() => import('../components/DevPanel')) : null;

export default function InboxPage() {
  const authed = useAuthStore((s) => Boolean(s.token));
  const isMock = useAuthStore((s) => s.isMock);
  const hasActive = useInboxStore((s) => s.activeDialogueUuid !== null);
  const source = useInboxStore((s) => s.source);
  const dialogueCount = useInboxStore((s) => s.dialogues.length);
  const [offline, setOffline] = useState(false);

  // Дані: реальні з API; демо — лише при вході без сервера (dev)
  useEffect(() => {
    const s = useInboxStore.getState();
    if (isMock) s.setDialogues(mockDialogues, mockMessages, 'mock');
    else void s.loadDialogues();
  }, [isMock]);

  // Пропозиції AI для бейджів у списку: 20 найсвіжіших діалогів (решта — при відкритті).
  // Лише коли змінюється кількість діалогів (перше завантаження, новий діалог), без опитування.
  useEffect(() => {
    if (source !== 'api' || dialogueCount === 0) return;
    const ai = useAIStore.getState();
    const recent = useInboxStore.getState().dialogues.slice(0, BULK_PENDING_LIMIT);
    Promise.all(recent.map((d) => ai.fetchPending(d.uuid))).catch((err) =>
      console.warn('Failed to fetch pending AI for dialogues:', err),
    );
  }, [source, dialogueCount]);

  // Realtime
  useEffect(() => {
    const token = useAuthStore.getState().token;
    if (!authed || isMock || !token) return;
    const s = useInboxStore.getState();
    connect(token, {
      onNewMessage: (e) => {
        const r = s.handleWsNewMessage(e);
        if (r.needsResync) void s.loadDialogues();
        if (r.notify) toast.info(`Нове повідомлення від ${r.clientName ?? 'клієнта'}`);
      },
      onMessageStatus: (e) => {
        s.handleWsMessageStatus(e);
        if (e.status === 'failed') toast.error('Повідомлення не доставлено');
      },
      onDialogueUpdated: s.handleWsDialogueUpdated,
      onDisconnect: () => setOffline(true),
      onReconnect: () => {
        setOffline(false);
        void s.loadDialogues(); // дозавантажити пропущене під час обриву
      },
    });
    return disconnect;
  }, [authed, isMock]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* < 900px: бокова панель прихована, лого і вихід — у шапці списку */}
      <div className="hidden min-[900px]:flex">
        <Sidebar active="chats" />
      </div>
      {/* < 900px: або список, або чат */}
      <ChatList className={cn(hasActive && 'hidden min-[900px]:flex')} />
      <ActiveChat className={cn(!hasActive && 'hidden min-[900px]:flex')} />

      {offline && (
        <div
          role="status"
          className="fixed left-1/2 top-3 z-50 flex -translate-x-1/2 items-center gap-2 rounded-pill bg-warn px-4 py-1.5 text-xs font-semibold text-white shadow-lg"
        >
          <WifiOff size={14} aria-hidden="true" />
          Немає з'єднання з сервером — перепідключення…
        </div>
      )}
      {isMock && (
        <div className="pointer-events-none fixed bottom-3 right-3 hidden rounded-full bg-gold-tint px-3 py-1 text-2xs font-semibold text-gold shadow min-[900px]:block">
          Демо-режим: сервер не запущено
        </div>
      )}
      {DevPanel && source === 'api' && (
        <Suspense fallback={null}>
          <DevPanel />
        </Suspense>
      )}
    </div>
  );
}
