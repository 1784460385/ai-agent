import { Menu, Plus, Settings } from 'lucide-react';
import { useState } from 'react';
import { ChatWindow } from '../components/chat/ChatWindow';
import { MobileDrawer } from '../components/layout/MobileDrawer';
import { Sidebar } from '../components/layout/Sidebar';
import { useChat } from '../hooks/useChat';
import { useMediaQuery } from '../hooks/useMediaQuery';

const KEY_STORAGE = 'deepseek_api_key';
const MODEL_STORAGE = 'deepseek_model';

export function ChatPage() {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem(KEY_STORAGE) || '');
  const [modelName, setModelName] = useState(() => sessionStorage.getItem(MODEL_STORAGE) || 'deepseek-flash');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [debug, setDebug] = useState(false);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const chat = useChat(apiKey, modelName);

  const openSettings = () => {
    if (isDesktop) {
      document.getElementById('api-settings')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    setDrawerOpen(true);
  };

  const sidebar = (
    <Sidebar
      saved={Boolean(apiKey)}
      modelName={modelName}
      onSave={(key, model) => {
        sessionStorage.setItem(KEY_STORAGE, key);
        sessionStorage.setItem(MODEL_STORAGE, model);
        setApiKey(key);
        setModelName(model);
        setDrawerOpen(false);
      }}
    />
  );

  return (
    <div className="flex h-full overflow-hidden bg-slate-50">
      <aside className="hidden h-full w-80 shrink-0 lg:block">{sidebar}</aside>
      <MobileDrawer open={drawerOpen && !isDesktop} onClose={() => setDrawerOpen(false)}>
        {sidebar}
      </MobileDrawer>
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 items-center justify-between border-b border-slate-200 bg-white/80 px-4">
          <div className="flex items-center gap-2">
            <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" aria-label="打开设置" onClick={() => setDrawerOpen(true)}>
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="text-base font-semibold text-slate-900">知识库问答</h1>
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
            <button type="button" aria-label="新对话" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" onClick={chat.startNew}>
              <Plus className="h-4 w-4" />
            </button>
            <button type="button" aria-label="设置" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100" onClick={openSettings}>
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
