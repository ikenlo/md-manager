import ChatList from '../components/ChatList';
import ChatView from '../components/ChatView';
import Sidebar from '../components/Sidebar';
import { useAuth } from '../store/auth';

export default function InboxPage() {
  const isMock = useAuth((s) => s.isMock);
  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar active="chats" />
      <ChatList />
      <ChatView />
      {isMock && (
        <div className="fixed bottom-3 right-3 rounded-full bg-gold-tint px-3 py-1 text-[11px] font-semibold text-gold shadow-card">
          Демо-режим: сервер не запущено
        </div>
      )}
    </div>
  );
}
