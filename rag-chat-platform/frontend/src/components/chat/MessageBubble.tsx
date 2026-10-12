import { Bot } from 'lucide-react';
import { motion } from 'framer-motion';
import type { Message } from '../../hooks/useChat';
import { CitationCard } from './CitationCard';
import { MarkdownRenderer } from './MarkdownRenderer';
import { RouterBadge } from './RouterBadge';

interface Props {
  message: Message;
  streaming?: boolean;
  debug?: boolean;
}

const NO_KB_NOTICE = '知识库中没有可引用的内容';

export function MessageBubble({ message, streaming = false, debug = false }: Props) {
  const isUser = message.role === 'user';
  const generatedWithoutKb = !isUser && message.content.includes(NO_KB_NOTICE);
  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      {!isUser && (
        <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-orange-100 p-2 text-orange-600">
          <Bot className="h-4 w-4" />
        </span>
      )}
      <div className={isUser ? 'max-w-[85%]' : 'max-w-[85%] min-w-0 flex-1'}>
        {!isUser && message.router && <RouterBadge router={message.router} />}
        <div
          className={
            isUser
              ? 'rounded-2xl rounded-tr-sm bg-indigo-600 p-4 text-white shadow-sm'
              : `rounded-2xl rounded-tl-sm border border-slate-200 bg-white p-4 shadow-sm ${
                  message.error ? 'border-red-200 bg-red-50 text-red-700' : ''
                }`
          }
        >
          {isUser && !!message.attachments?.length && (
            <div className="mb-2 flex flex-wrap gap-1">
              {message.attachments.map((item) => (
                <span key={item.name} className="rounded-full bg-white/15 px-2 py-0.5 text-xs">
                  {item.name}
                </span>
              ))}
            </div>
          )}
          {isUser ? (
            message.content ? <p className="text-sm leading-7 whitespace-pre-wrap">{message.content}</p> : null
          ) : message.content ? (
            message.error ? (
              <p className="text-sm leading-7 whitespace-pre-wrap">{message.content}</p>
            ) : (
              <MarkdownRenderer content={message.content} />
            )
          ) : streaming ? (
            <div className="space-y-2" aria-hidden="true">
              <div className="h-3 w-40 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-64 animate-pulse rounded bg-slate-200" />
              <div className="h-3 w-52 animate-pulse rounded bg-slate-200" />
            </div>
          ) : (
            <p className="text-sm text-slate-400">…</p>
          )}
          {streaming && message.content && (
            <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-orange-500 align-middle" />
          )}
        </div>
        {!isUser && !generatedWithoutKb && message.sources && message.sources.length > 0 && (
          <CitationCard sources={message.sources} expanded={debug} />
        )}
      </div>
    </motion.article>
  );
}
