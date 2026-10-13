import { FileJson, FileSpreadsheet, FileText, Presentation, RotateCw, Trash2 } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import type { DocumentInfo } from '../../api/client';
import { fileKind, formatSize } from './status';

function fileIcon(name: string) {
  const ext = fileKind(name);
  if (ext === 'pdf') return { Icon: FileText, className: 'text-red-400' };
  if (ext === 'doc' || ext === 'docx') return { Icon: FileText, className: 'text-blue-400' };
  if (ext === 'xls' || ext === 'xlsx' || ext === 'csv') return { Icon: FileSpreadsheet, className: 'text-emerald-400' };
  if (ext === 'ppt' || ext === 'pptx') return { Icon: Presentation, className: 'text-orange-400' };
  if (ext === 'json' || ext === 'ipynb') return { Icon: FileJson, className: 'text-amber-300' };
  return { Icon: FileText, className: 'text-slate-400' };
}

function statusText(file: DocumentInfo) {
  if (file.parse_status === 'parsing') return '解析中';
  if (file.parse_status === 'indexed') return '索引完成';
  if (file.parse_status === 'failed') return file.parse_error || '解析失败';
  return '未索引';
}

interface Props {
  files: DocumentInfo[];
  selected: string[];
  department: string;
  onToggle: (filename: string) => void;
  onToggleAll: () => void;
  onPreview: (filename: string) => void;
  onDelete: (filename: string) => void;
  onRetry: (filename: string) => void;
  onDragStart: (filename: string) => void;
}

const ITEM_HEIGHT = 64;
const VIEWPORT = 480;

export function FileList({
  files,
  selected,
  department,
  onToggle,
  onToggleAll,
  onPreview,
  onDelete,
  onRetry,
  onDragStart,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const virtual = files.length > 50;
  const start = virtual ? Math.max(0, Math.floor(scrollTop / ITEM_HEIGHT) - 2) : 0;
  const end = virtual ? Math.min(files.length, start + Math.ceil(VIEWPORT / ITEM_HEIGHT) + 4) : files.length;
  const visible = useMemo(() => files.slice(start, end), [files, start, end]);

  if (!files.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 px-6 py-16 text-center">
        <FileText className="mb-3 h-8 w-8 text-slate-600" />
        <p className="text-sm font-semibold text-slate-100">此文件夹还没有文件</p>
        <p className="mt-1 text-xs text-slate-500">拖拽文件到上方区域开始导入吧。</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between px-1">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          <input
            type="checkbox"
            checked={selected.length === files.length}
            aria-label="全选文件"
            onChange={onToggleAll}
            className="rounded border-slate-600 bg-slate-900 text-orange-500 focus:ring-orange-500"
          />
          文件列表
        </label>
        <span className="text-xs text-slate-500">{files.length} 个文件</span>
      </div>
      <div
        ref={scroller}
        className={virtual ? 'overflow-y-auto' : ''}
        style={virtual ? { maxHeight: VIEWPORT } : undefined}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      >
        <ul className="space-y-1" style={virtual ? { height: files.length * ITEM_HEIGHT, position: 'relative' } : undefined}>
          {visible.map((file, index) => {
            const { Icon, className } = fileIcon(file.name);
            const status = statusText(file);
            const offset = virtual ? (start + index) * ITEM_HEIGHT : undefined;
            return (
              <li
                key={file.name}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData('text/plain', `kb-file:${department}:${file.name}`);
                  event.dataTransfer.effectAllowed = 'move';
                  onDragStart(file.name);
                }}
                className="group flex items-center justify-between rounded-lg p-3 hover:bg-slate-800"
                style={virtual ? { position: 'absolute', top: offset, left: 0, right: 0, height: ITEM_HEIGHT } : undefined}
              >
                <span className="flex min-w-0 items-center gap-3">
                  <input
                    type="checkbox"
                    checked={selected.includes(file.name)}
                    aria-label={`选择 ${file.name}`}
                    onChange={() => onToggle(file.name)}
                    className="rounded border-slate-600 bg-slate-900 text-orange-500 focus:ring-orange-500"
                  />
                  <Icon className={`h-4 w-4 shrink-0 ${className}`} />
                  <button
                    type="button"
                    className="min-w-0 text-left"
                    aria-label={`预览 ${file.name}`}
                    onClick={() => onPreview(file.name)}
                  >
                    <span className="block truncate text-sm font-medium text-slate-100">{file.name}</span>
                    <span
                      className={`block text-xs ${
                        file.parse_status === 'failed'
                          ? 'text-red-300'
                          : file.parse_status === 'parsing'
                            ? 'text-amber-300'
                            : file.parse_status === 'indexed'
                              ? 'text-emerald-400'
                              : 'text-slate-500'
                      }`}
                    >
                      {status}
                    </span>
                  </button>
                </span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-slate-500">
                  {formatSize(file.size)}
                  <button
                    type="button"
                    aria-label={`重新索引 ${file.name}`}
                    className="rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-700 hover:text-orange-300 group-hover:opacity-100 focus:opacity-100"
                    onClick={() => onRetry(file.name)}
                  >
                    <RotateCw className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label={`删除 ${file.name}`}
                    className="rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-700 hover:text-red-300 group-hover:opacity-100 focus:opacity-100"
                    onClick={() => onDelete(file.name)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
