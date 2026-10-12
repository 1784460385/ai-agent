import { MoreHorizontal, Plus, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { ConversationSummary } from '../../api/client';

const GROUPS = ['今天', '昨天', '7天内', '30天内', '更早'] as const;

function groupConversations(items: ConversationSummary[]) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfToday.getDate() - 1);
  const withinSeven = new Date(startOfToday);
  withinSeven.setDate(startOfToday.getDate() - 7);
  const withinThirty = new Date(startOfToday);
  withinThirty.setDate(startOfToday.getDate() - 30);
  const groups: Record<(typeof GROUPS)[number], ConversationSummary[]> = {
    今天: [],
    昨天: [],
    '7天内': [],
    '30天内': [],
    更早: [],
  };
  for (const item of items) {
    const time = new Date(item.updated_at);
    if (Number.isNaN(time.getTime()) || time >= startOfToday) groups['今天'].push(item);
    else if (time >= startOfYesterday) groups['昨天'].push(item);
    else if (time >= withinSeven) groups['7天内'].push(item);
    else if (time >= withinThirty) groups['30天内'].push(item);
    else groups['更早'].push(item);
  }
  return GROUPS.map((label) => ({ label, items: groups[label] })).filter((group) => group.items.length);
}

interface Props {
  items: ConversationSummary[];
  activeId: number | null;
  onNew: () => void;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}

export function ConversationSidebar({ items, activeId, onNew, onSelect, onDelete }: Props) {
  const [searching, setSearching] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [menuId, setMenuId] = useState<number | null>(null);
  const visible = useMemo(() => {
    const text = keyword.trim();
    if (!text) return items;
    return items.filter((item) => item.title.includes(text));
  }, [items, keyword]);
  const groups = groupConversations(visible);

  return (
    <div className="flex h-full flex-col bg-[#f7f7f8] text-slate-800">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <strong className="text-lg font-semibold tracking-tight">星澜</strong>
        <button
          type="button"
          aria-label="搜索对话"
          className="rounded-lg p-1.5 text-slate-500 hover:bg-white"
          onClick={() => setSearching((value) => !value)}
        >
          <Search className="h-4 w-4" />
        </button>
      </div>
      <div className="px-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm shadow-sm hover:bg-slate-50"
        >
          <Plus className="h-4 w-4 rounded-full" />
          开启新对话
        </button>
        {searching && (
          <input
            autoFocus
            value={keyword}
            aria-label="搜索对话标题"
            placeholder="搜索对话"
            onChange={(event) => setKeyword(event.target.value)}
            className="mt-3 w-full rounded-full border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-200"
          />
        )}
      </div>
      <div className="mt-3 flex-1 overflow-y-auto px-2 pb-4">
        {!groups.length && <p className="px-3 py-6 text-center text-sm text-slate-400">还没有对话</p>}
        {groups.map((group) => (
          <section key={group.label} className="mt-3">
            <h2 className="px-3 py-1 text-xs text-slate-400">{group.label}</h2>
            <ul>
              {group.items.map((item) => {
                const active = item.id === activeId;
                return (
                  <li key={item.id} className="relative">
                    <div
                      className={`group flex w-full items-center rounded-lg pr-1 text-sm ${
                        active ? 'bg-[#ebe9fe]' : 'hover:bg-white'
                      }`}
                    >
                      <button type="button" onClick={() => onSelect(item.id)} className="min-w-0 flex-1 truncate px-3 py-2 text-left">
                        {item.title}
                      </button>
                      <button
                        type="button"
                        aria-label={`${item.title} 的更多操作`}
                        className={`rounded p-1 text-slate-400 ${active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        onClick={() => setMenuId((current) => (current === item.id ? null : item.id))}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                    </div>
                    {menuId === item.id && (
                      <button
                        type="button"
                        className="absolute top-9 right-2 z-10 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-red-600 shadow-md"
                        onClick={() => {
                          setMenuId(null);
                          onDelete(item.id);
                        }}
                      >
                        删除
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
