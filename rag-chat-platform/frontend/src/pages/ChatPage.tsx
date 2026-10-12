import { Menu, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChatWindow } from '../components/chat/ChatWindow';
import { ConversationSidebar } from '../components/chat/ConversationSidebar';
import { MobileDrawer } from '../components/layout/MobileDrawer';
import { ApiKeyCard } from '../components/settings/ApiKeyCard';
import { useAuth } from '../auth/AuthContext';
import { useChat } from '../hooks/useChat';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { readApiKey, saveApiKey } from '../lib/apiKeyStorage';

export function ChatPage() {
  const { user } = useAuth();
  const stored = readApiKey(user?.id ?? 0);
  const [apiKey, setApiKey] = useState(stored.apiKey);
  const [modelName, setModelName] = useState(stored.modelName);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [debug, setDebug] = useState(false);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const [params, setParams] = useSearchParams();
  const chat = useChat(apiKey, modelName);

  useEffect(() => {
    if (!user) return;
    const next = readApiKey(user.id);
    setApiKey(next.apiKey);
    setModelName(next.modelName);
  }, [user]);

  useEffect(() => {
    const raw = params.get('conversation');
    const id = Number(raw);
    if (!raw || !id) return;
    void chat.openConversation(id).finally(() => setParams({}, { replace: true }));
  }, [params, chat.openConversation, setParams]);

  const saveKey = (key: string, model: string) => {
    if (!user) return;
    saveApiKey(user.id, key, model);
    setApiKey(key);
    setModelName(model);
    setSettingsOpen(false);
  };

  const history = (
    <ConversationSidebar
      items={chat.conversations}
      activeId={chat.conversationId}
      onNew={() => {
        chat.startNew();
        setHistoryOpen(false);
      }}
      onSelect={(id) => {
        void chat.openConversation(id);
        setHistoryOpen(false);
      }}
      onDelete={(id) => {
        if (!window.confirm('删除这则对话？')) return;
        void chat.removeConversation(id);
      }}
    />
  );

  return (
    <div className="flex h-full overflow-hidden bg-white">
      <aside className="hidden h-full w-[280px] shrink-0 flex-col border-r border-slate-200 lg:flex">
        <div className="min-h-0 flex-1">{history}</div>
        <div className="border-t border-slate-200 bg-slate-900 p-3">
          <ApiKeyCard saved={Boolean(apiKey)} modelName={modelName} onSave={saveKey} />
        </div>
      </aside>
      <MobileDrawer open={historyOpen && !isDesktop} onClose={() => setHistoryOpen(false)}>
        {history}
      </MobileDrawer>
      <MobileDrawer open={settingsOpen && !isDesktop} onClose={() => setSettingsOpen(false)}>
        <div className="h-full overflow-y-auto bg-slate-900 p-4">
          <ApiKeyCard saved={Boolean(apiKey)} modelName={modelName} onSave={saveKey} />
        </div>
      </MobileDrawer>
      <section className="flex min-w-0 flex-1 flex-col bg-slate-50">
        <div className="flex h-14 items-center justify-between border-b border-slate-200 bg-white/80 px-4">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
              aria-label="打开历史对话"
              onClick={() => setHistoryOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="truncate text-base font-semibold text-slate-900">
              {chat.conversations.find((item) => item.id === chat.conversationId)?.title || '知识库问答'}
            </h1>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-pressed={debug}
              aria-label="调试模式"
              className={`rounded-lg px-2 py-1 text-xs ${debug ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:bg-slate-100'}`}
              onClick={() => setDebug((value) => !value)}
            >
              调试
            </button>
            <button
              type="button"
              aria-label="设置"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings className="h-4 w-4" />
            </button>
          </div>
        </div>
        <ChatWindow
          messages={chat.messages}
          isLoading={chat.isLoading}
          error={chat.error}
          hasApiKey={Boolean(apiKey)}
          debug={debug}
          onSend={chat.sendMessage}
          onStop={chat.stop}
        />
      </section>
    </div>
  );
}
