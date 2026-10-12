import { useEffect, useRef, useState } from 'react';
import type { Message } from '../hooks/useChat';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  hasApiKey: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function ChatWindow({ messages, isLoading, error, hasApiKey, onSend, onStop }: Props) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  const submit = () => {
    const text = draft.trim();
    if (!text || isLoading) return;
    onSend(text);
    setDraft('');
  };

  return (
    <section className="chat">
      <header className="chat-bar">
        <div>
          <p className="eyebrow">本地知识库 · DeepSeek</p>
          <h1>知识库问答</h1>
        </div>
        <p className={hasApiKey ? 'status on' : 'status'}>{hasApiKey ? 'Key 已就绪' : '等待 API Key'}</p>
      </header>

      <div className="transcript">
        {messages.length === 0 && (
          <div className="empty">
            <h2>先索引资料，再提问</h2>
            <p>回答只依据知识库里的片段。资料里没有的内容，会直接说明无法回答。</p>
            <div className="suggestions">
              {['客服邮箱是什么？', '年假有几天？', '超出免费额度怎么收费？'].map((item) => (
                <button key={item} type="button" onClick={() => onSend(item)} disabled={!hasApiKey}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message, index) => (
          <MessageBubble
            key={`${message.role}-${index}`}
            message={message}
            streaming={isLoading && index === messages.length - 1 && message.role === 'assistant'}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        {error && <p className="composer-error">{error}</p>}
        <textarea
          ref={boxRef}
          value={draft}
          maxLength={4000}
          rows={3}
          placeholder={hasApiKey ? '问一个知识库里可能有答案的问题' : '请先在左侧保存 API Key'}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-actions">
          <span>{draft.length}/4000</span>
          {isLoading ? (
            <button type="button" className="btn btn-stop" onClick={onStop}>
              停止
            </button>
          ) : (
            <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>
              发送
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
