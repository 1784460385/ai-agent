import { FileJson, FileSpreadsheet, FileText, Presentation, RotateCw, Trash2 } from 'lucide-react';
import type { DocumentInfo } from '../../api/client';

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
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
  return '';
}

interface Props {
  files: DocumentInfo[];
  onDelete: (filename: string) => void;
  onRetry: (filename: string) => void;
}

export function FileList({ files, onDelete, onRetry }: Props) {
  if (!files.length) {
    return <p className="px-2 py-1 text-xs text-slate-500">还没有文档</p>;
  }
  return (
    <ul className="space-y-1">
      {files.map((file) => {
        const { Icon, className } = fileIcon(file.name);
        const status = statusText(file);
        return (
          <li key={file.name} className="group rounded-lg p-2 text-sm hover:bg-slate-800">
            <div className="flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2 text-slate-200">
                <Icon className={`h-4 w-4 shrink-0 ${className}`} />
                <span className="truncate">{file.name}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-xs text-slate-500">
                {formatSize(file.size)}
                {file.parse_status === 'failed' && (
                  <button
                    type="button"
                    aria-label={`重试 ${file.name}`}
                    className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-orange-300"
                    onClick={() => onRetry(file.name)}
                  >
                    <RotateCw className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  aria-label={`删除 ${file.name}`}
                  className="rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-700 hover:text-red-300 group-hover:opacity-100"
                  onClick={() => onDelete(file.name)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </span>
            </div>
            {status && (
              <p
                className={`mt-1 pl-6 text-xs ${
                  file.parse_status === 'failed'
                    ? 'text-red-300'
                    : file.parse_status === 'parsing'
                      ? 'text-amber-300'
                      : 'text-emerald-400'
                }`}
              >
                {status}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
