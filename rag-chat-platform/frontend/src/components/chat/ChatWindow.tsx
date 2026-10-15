import { useEffect, useRef, useState } from 'react';
import type { Message } from '../../hooks/useChat';
import { ChatInput } from './ChatInput';
import { ConversationOutline } from './ConversationOutline';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  hasApiKey: boolean;
  debug: boolean;
  onSend: (text: string, files?: File[]) => void;
  onStop: () => void;
}

const SUGGESTIONS = ['工资怎么算？', '入职需要准备什么？', '产品版本号是多少？'];

export function ChatWindow({ messages, isLoading, error, hasApiKey, debug, onSend, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollRoot, setScrollRoot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setScrollRoot(scrollRef.current);
  }, []);

  // 仅在生成中跟随到底；手动点目录跳转时不被打断
  useEffect(() => {
    if (!isLoading) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isLoading]);

  return (
    <>
      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-6 md:px-8">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
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
              <div key={`${message.role}-${index}`} id={`msg-${index}`} className="scroll-mt-4">
                <MessageBubble
                  message={message}
                  debug={debug}
                  streaming={isLoading && index === messages.length - 1 && message.role === 'assistant'}
                />
              </div>
            ))}
            {error && <p className="text-center text-sm text-red-600">{error}</p>}
            <div ref={bottomRef} />
          </div>
        </div>
        {/* 与输入框同一套 px + max-w-6xl，目录挂在内容列右侧，不挤占输出宽度 */}
        <div className="pointer-events-none absolute inset-0 hidden px-4 md:px-8 xl:block">
          <div className="relative mx-auto h-full w-full max-w-6xl">
            <ConversationOutline messages={messages} scrollRoot={scrollRoot} />
          </div>
        </div>
      </div>
      <ChatInput disabled={!hasApiKey} loading={isLoading} onSend={onSend} onStop={onStop} />
    </>
  );
}
