import { useState } from 'react';
import { ApiKeyPanel } from './components/ApiKeyPanel';
import { ChatWindow } from './components/ChatWindow';
import { KnowledgeUpload } from './components/KnowledgeUpload';
import { useChat } from './hooks/useChat';

export default function App() {
  const [apiKey, setApiKey] = useState('');
  const [modelName, setModelName] = useState('deepseek-flash');
  const chat = useChat(apiKey, modelName);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <strong>星澜</strong>
            <p>RAG 问答台</p>
          </div>
        </div>
        <ApiKeyPanel
          saved={Boolean(apiKey)}
          modelName={modelName}
          onSave={(key, model) => {
            setApiKey(key);
            setModelName(model);
          }}
        />
        <KnowledgeUpload />
      </aside>
      <main>
        <ChatWindow
          messages={chat.messages}
          isLoading={chat.isLoading}
          error={chat.error}
          hasApiKey={Boolean(apiKey)}
          onSend={chat.sendMessage}
          onStop={chat.stop}
        />
      </main>
    </div>
  );
}
