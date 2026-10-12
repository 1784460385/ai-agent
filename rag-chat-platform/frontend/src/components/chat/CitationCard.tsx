import { ChevronDown, Paperclip } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { SourceItem } from '../../api/client';

interface Props {
  sources: SourceItem[];
  expanded?: boolean;
}

export function CitationCard({ sources, expanded = false }: Props) {
  const [open, setOpen] = useState(expanded);
  const [active, setActive] = useState<SourceItem | null>(null);

  useEffect(() => {
    if (expanded) setOpen(true);
  }, [expanded]);
  if (!sources.length) return null;

  return (
    <>
      <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <button
          type="button"
          className="flex w-full items-center justify-between px-3 py-2 text-left text-sm text-slate-700"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <span className="inline-flex items-center gap-2">
            <Paperclip className="h-4 w-4 text-slate-400" />
            引用来源 ({sources.length})
          </span>
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
          {sources.map((source) => source.source).join('、')}
        </div>
        {open && (
          <div className="space-y-2 border-t border-slate-100 p-3">
            {sources.map((source) => (
              <article key={source.index} className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
                <p className="font-medium text-slate-800">
                  {source.index}. {source.source}
                </p>
                <p className="mt-1 leading-6">{source.preview}</p>
                <button
                  type="button"
                  className="mt-2 text-xs text-orange-600 hover:underline"
                  onClick={() => setActive(source)}
                >
                  查看原文
                </button>
              </article>
            ))}
          </div>
        )}
      </div>
      {active && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={() => setActive(null)}>
          <aside
            className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <p className="text-xs text-slate-500">{active.department_name}</p>
                <h3 className="text-lg font-semibold text-slate-900">{active.source}</h3>
              </div>
              <button type="button" className="text-sm text-slate-500" aria-label="关闭原文" onClick={() => setActive(null)}>
                关闭
              </button>
            </div>
            <p className="rounded-lg bg-orange-50 p-4 text-sm leading-7 whitespace-pre-wrap text-slate-700">
              {active.excerpt || active.preview}
            </p>
          </aside>
        </div>
      )}
    </>
  );
}
