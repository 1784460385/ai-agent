import { useEffect, useState } from 'react';
import { clearHistory, deleteHistory, listHistory, type HistoryItem } from '../api/client';
import { Button } from '../components/ui/Button';

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

export function HistoryPage() {
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const size = 20;
  const pages = Math.max(1, Math.ceil(total / size));

  const load = async (nextPage: number, nextQuery: string) => {
    const result = await listHistory(nextPage, size, nextQuery);
    setItems(result.items);
    setTotal(result.total);
    setPage(result.page);
  };

  useEffect(() => {
    load(page, query).catch((err) => setError(err instanceof Error ? err.message : '无法读取历史记录'));
  }, [page, query]);

  const search = () => {
    setPage(1);
    setQuery(keyword.trim());
  };

  const remove = async (id: number) => {
    if (!window.confirm('删除这条历史记录？')) return;
    await deleteHistory(id);
    await load(page, query);
  };

  const clearAll = async () => {
    if (!window.confirm('清空全部历史记录？此操作不可恢复。')) return;
    await clearHistory();
    setPage(1);
    await load(1, query);
  };

  return (
    <div className="h-full overflow-y-auto bg-slate-50">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold text-slate-900">历史记录</h1>
          <Button variant="danger" disabled={!total} onClick={() => void clearAll()}>
            清空全部
          </Button>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            search();
          }}
        >
          <input
            value={keyword}
            placeholder="搜索问题"
            aria-label="搜索问题"
            onChange={(event) => setKeyword(event.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-orange-500"
          />
          <Button type="submit">搜索</Button>
        </form>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!items.length && !error && <p className="rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">还没有历史记录，去问点什么吧</p>}
        <ul className="space-y-3">
          {items.map((item) => {
            const open = openId === item.id;
            return (
              <li key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <button type="button" className="w-full text-left" onClick={() => setOpenId(open ? null : item.id)}>
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-medium text-slate-900">{item.question}</p>
                    <time className="shrink-0 text-xs text-slate-400">{formatTime(item.created_at)}</time>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {item.router_departments.map((name) => (
                      <span key={name} className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600">
                        {name}
                      </span>
                    ))}
                  </div>
                </button>
                {open && (
                  <div className="mt-3 border-t border-slate-100 pt-3">
                    <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{item.answer}</p>
                    {!!item.citations?.length && (
                      <ul className="mt-3 space-y-2">
                        {item.citations.map((citation, index) => (
                          <li key={`${citation.file}-${index}`} className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">
                            <strong className="text-slate-800">{citation.file}</strong>
                            <p className="mt-1">{citation.snippet}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                    <Button className="mt-3" variant="danger" onClick={() => void remove(item.id)}>
                      删除
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {total > size && (
          <div className="flex items-center justify-center gap-3 text-sm text-slate-600">
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
              上一页
            </Button>
            <span>
              {page} / {pages}
            </span>
            <Button variant="ghost" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>
              下一页
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
