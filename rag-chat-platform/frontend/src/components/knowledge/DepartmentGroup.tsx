import { ChevronDown, Folder, Trash2 } from 'lucide-react';
import type { DepartmentInfo } from '../../api/client';
import { Button } from '../ui/Button';
import { FileList } from './FileList';

interface Props {
  department: DepartmentInfo;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  onIndex: () => void;
  onDelete: (filename: string) => void;
  onRetry: (filename: string) => void;
  onRemoveFolder: () => void;
}

export function DepartmentGroup({
  department,
  open,
  busy,
  onToggle,
  onIndex,
  onDelete,
  onRetry,
  onRemoveFolder,
}: Props) {
  return (
    <section className="rounded-xl bg-slate-800/70">
      <div className="flex w-full items-center justify-between px-3 py-2">
        <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" aria-expanded={open} onClick={onToggle}>
          <Folder className="h-4 w-4 shrink-0 text-orange-300" />
          <span>
            <span className="block text-sm text-slate-100">{department.name}</span>
            <span className="text-xs text-slate-500">
              {department.files.length} 个文件 · {department.chunk_count} 片段
            </span>
          </span>
        </button>
        <span className="flex items-center gap-1">
          <button
            type="button"
            aria-label={`删除文件夹 ${department.name}`}
            className="rounded p-1 text-slate-500 hover:bg-slate-700 hover:text-red-300"
            onClick={onRemoveFolder}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button type="button" aria-label={open ? '收起文件夹' : '展开文件夹'} onClick={onToggle}>
            <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
        </span>
      </div>
      {open && (
        <div className="space-y-2 px-2 pb-3">
          <FileList files={department.files} onDelete={onDelete} onRetry={onRetry} />
          <Button variant="secondary" className="w-full" disabled={busy} onClick={onIndex}>
            重建此文件夹索引
          </Button>
        </div>
      )}
    </section>
  );
}
