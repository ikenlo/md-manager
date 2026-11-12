import { useEffect } from 'react';
import ActiveChat from '../components/ActiveChat';
import ChatList from '../components/ChatList';
import Sidebar from '../components/Sidebar';
import { cn } from '../components/ui';
import { mockDialogues, mockMessages } from '../data/mock';
import { connect, disconnect } from '../lib/ws';
import { useAuthStore } from '../store/auth';
import { useInboxStore } from '../store/inbox';

export default function InboxPage() {
  const token = useAuthStore((s) => s.token);
  const isMock = useAuthStore((s) => s.isMock);
  const hasActive = useInboxStore((s) => s.activeDialogueUuid !== null);

  // Поки немає реального джерела (Фаза 2: WebSocket + API) — демо-дані як запасний варіант
  useEffect(() => {
    const s = useInboxStore.getState();
    if (s.dialogues.length === 0) s.setDialogues(mockDialogues, mockMessages);
  }, []);

  useEffect(() => {
    if (!token || isMock) return;
    const s = useInboxStore.getState();
    connect(token, {
      onNewMessage: s.appendIncomingMessage,
      onDialogueUpdated: s.upsertDialogue,
      onMessageStatus: s.setMessageStatus,
    });
    return disconnect;
  }, [token, isMock]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* < 900px: бокова панель прихована, лого і вихід — у шапці списку */}
      <div className="hidden min-[900px]:flex">
        <Sidebar active="chats" />
      </div>
      {/* < 900px: або список, або чат */}
      <ChatList className={cn(hasActive && 'hidden min-[900px]:flex')} />
      <ActiveChat className={cn(!hasActive && 'hidden min-[900px]:flex')} />
      {isMock && (
        <div className="pointer-events-none fixed bottom-3 right-3 hidden rounded-full bg-gold-tint px-3 py-1 text-2xs font-semibold text-gold shadow min-[900px]:block">
          Демо-режим: сервер не запущено
        </div>
      )}
    </div>
  );
}
