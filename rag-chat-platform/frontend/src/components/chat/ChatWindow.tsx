import { useEffect, useRef } from 'react';
import type { Message } from '../../hooks/useChat';
import { ChatInput } from './ChatInput';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  hasApiKey: boolean;
  debug: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

const SUGGESTIONS = ['工资怎么算？', '入职需要准备什么？', '产品版本号是多少？'];

export function ChatWindow({ messages, isLoading, error, hasApiKey, debug, onSend, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.length === 0 && (
            <div className="mx-auto mt-16 max-w-xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
              <h2 className="text-2xl font-semibold text-slate-900">按文件夹检索，再回答</h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                问题会先匹配你建好的知识库文件夹。资料里有依据就按原文回答；没有依据时，由模型自行生成，并标明没有知识库引用，需自行判断准确性。
              </p>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((item) => (
                  <button
                    key={item}
                    type="button"
                    disabled={!hasApiKey}
                    className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:border-orange-300 disabled:opacity-50"
                    onClick={() => onSend(item)}
                  >
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
              debug={debug}
              streaming={isLoading && index === messages.length - 1 && message.role === 'assistant'}
            />
          ))}
          {error && <p className="text-center text-sm text-red-600">{error}</p>}
          <div ref={bottomRef} />
        </div>
      </div>
      <ChatInput disabled={!hasApiKey} loading={isLoading} onSend={onSend} onStop={onStop} />
    </>
  );
}
