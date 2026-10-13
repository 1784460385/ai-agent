import { Menu, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { listApiKeys, type ApiKeyItem } from '../api/client';
import { ChatWindow } from '../components/chat/ChatWindow';
import { ConversationSidebar } from '../components/chat/ConversationSidebar';
import { MobileDrawer } from '../components/layout/MobileDrawer';
import { useAuth } from '../auth/AuthContext';
import { useChat } from '../hooks/useChat';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { readSelectedKeyId, saveSelectedKeyId } from '../lib/apiKeyStorage';

export function ChatPage() {
  const { user } = useAuth();
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [keyId, setKeyId] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [debug, setDebug] = useState(false);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const [params, setParams] = useSearchParams();
  const chat = useChat(keyId);
  const current = keys.find((item) => item.id === keyId);

  useEffect(() => {
    if (!user) return;
    listApiKeys()
      .then((items) => {
        setKeys(items);
        const saved = readSelectedKeyId(user.id);
        const picked = items.find((item) => item.id === saved) || items.find((item) => item.is_default) || items[0];
        setKeyId(picked?.id ?? null);
      })
      .catch(() => {
        setKeys([]);
        setKeyId(null);
      });
  }, [user]);

  useEffect(() => {
    const raw = params.get('conversation');
    const id = Number(raw);
    if (!raw || !id) return;
    void chat.openConversation(id).finally(() => setParams({}, { replace: true }));
  }, [params, chat.openConversation, setParams]);

  const chooseKey = (id: number) => {
    if (!user) return;
    setKeyId(id);
    saveSelectedKeyId(user.id, id);
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
      </aside>
      <MobileDrawer open={historyOpen && !isDesktop} onClose={() => setHistoryOpen(false)}>
        {history}
      </MobileDrawer>
      <section className="flex min-w-0 flex-1 flex-col bg-slate-50">
        <div className="flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4">
          <div className="flex min-w-0 items-center gap-2">
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
          <div className="flex items-center gap-2">
            {keys.length > 0 ? (
              <label className="flex items-center gap-2 text-sm text-slate-600">
                当前配置
                <select
                  aria-label="切换 API Key"
                  value={keyId ?? ''}
                  onChange={(event) => chooseKey(Number(event.target.value))}
                  className="max-w-72 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-base text-slate-800 outline-none focus:ring-2 focus:ring-orange-500"
                >
                  {keys.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                      {item.is_default ? '（默认）' : ''} · {item.model}
                    </option>
                  ))}
                </select>
                <Link
                  to="/settings/keys"
                  aria-label="打开模型配置"
                  title="管理 API Key"
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                >
                  <Settings className="h-4 w-4" />
                </Link>
              </label>
            ) : (
              <Link to="/settings/keys" className="text-sm text-orange-600 hover:underline">
                请先配置 API Key
              </Link>
            )}
            <button
              type="button"
              aria-pressed={debug}
              aria-label="调试模式"
              className={`rounded-lg px-2 py-1 text-xs ${debug ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:bg-slate-100'}`}
              onClick={() => setDebug((value) => !value)}
            >
              调试
            </button>
          </div>
        </div>
        {current && <p className="sr-only">当前模型：{current.model}</p>}
        <ChatWindow
          messages={chat.messages}
          isLoading={chat.isLoading}
          error={chat.error}
          hasApiKey={Boolean(keyId)}
          debug={debug}
          onSend={chat.sendMessage}
          onStop={chat.stop}
        />
      </section>
    </div>
  );
}
