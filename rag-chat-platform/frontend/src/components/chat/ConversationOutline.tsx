import { useEffect, useMemo, useState } from 'react';
import type { Message } from '../../hooks/useChat';

interface OutlineItem {
  id: string;
  label: string;
}

interface Props {
  messages: Message[];
  scrollRoot: HTMLElement | null;
}

function turnLabel(message: Message) {
  const text = message.content.trim().replace(/\s+/g, ' ');
  if (text) return text.length > 18 ? `${text.slice(0, 18)}…` : text;
  const file = message.attachments?.[0]?.name;
  if (file) return file.length > 18 ? `${file.slice(0, 18)}…` : file;
  return '附件提问';
}

export function ConversationOutline({ messages, scrollRoot }: Props) {
  const items = useMemo<OutlineItem[]>(() => {
    return messages
      .map((message, index) => {
        if (message.role !== 'user') return null;
        return { id: `msg-${index}`, label: turnLabel(message) };
      })
      .filter((item): item is OutlineItem => Boolean(item));
  }, [messages]);

  const [activeId, setActiveId] = useState<string>('');

  useEffect(() => {
    if (!scrollRoot || items.length < 2) return;

    const elements = items
      .map((item) => document.getElementById(item.id))
      .filter((node): node is HTMLElement => Boolean(node));
    if (!elements.length) return;

    const visible = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id;
          if (entry.isIntersecting) visible.set(id, entry.intersectionRatio);
          else visible.delete(id);
        }
        if (!visible.size) return;
        const best = [...visible.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
        if (best) setActiveId(best);
      },
      {
        root: scrollRoot,
        rootMargin: '-12% 0px -55% 0px',
        threshold: [0.1, 0.35, 0.6],
      }
    );

    for (const el of elements) observer.observe(el);
    setActiveId((current) => current || items[0].id);
    return () => observer.disconnect();
  }, [items, scrollRoot, messages.length]);

  if (items.length < 2) return null;

  const jump = (id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setActiveId(id);
  };

  return (
    <nav
      aria-label="对话目录"
      className="pointer-events-none absolute top-8 bottom-8 left-full z-10 ml-3 hidden w-40 2xl:ml-4 2xl:w-44 xl:block"
    >
      <div className="pointer-events-auto sticky top-8 max-h-[min(28rem,60vh)] overflow-y-auto rounded-2xl border border-slate-200/80 bg-white/90 p-2.5 shadow-sm backdrop-blur">
        <ul className="space-y-0.5">
          {items.map((item) => {
            const active = item.id === activeId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  title={item.label}
                  onClick={() => jump(item.id)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
                    active ? 'bg-slate-100 text-slate-800' : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate text-xs leading-5">{item.label}</span>
                  <span className={`h-px w-3 shrink-0 ${active ? 'bg-orange-400' : 'bg-slate-300'}`} />
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}
