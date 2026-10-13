import { FolderOpen, Loader2, RefreshCw, RotateCw, Trash2 } from 'lucide-react';
import type { AppConfig, DepartmentInfo } from '../../api/client';
import { Button } from '../ui/Button';
import { FileList } from './FileList';
import { FileUploader } from './FileUploader';

interface Props {
  department?: DepartmentInfo;
  config: AppConfig | null;
  busy: 'upload' | 'index' | null;
  dragging: boolean;
  selectedFiles: string[];
  onDragging: (value: boolean) => void;
  onFiles: (files: File[]) => void;
  onIndex: () => void;
  onToggleFile: (filename: string) => void;
  onToggleAll: () => void;
  onPreview: (filename: string) => void;
  onDeleteFile: (filename: string) => void;
  onRetryFile: (filename: string) => void;
  onBatchDelete: () => void;
  onBatchRetry: () => void;
  onDragStart: (filename: string) => void;
}

export function FolderDetail({
  department,
  config,
  busy,
  dragging,
  selectedFiles,
  onDragging,
  onFiles,
  onIndex,
  onToggleFile,
  onToggleAll,
  onPreview,
  onDeleteFile,
  onRetryFile,
  onBatchDelete,
  onBatchRetry,
  onDragStart,
}: Props) {
  if (!department) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <FolderOpen className="mb-3 h-10 w-10 text-slate-600" />
        <p className="text-sm font-semibold text-slate-100">请先在左侧选择或新建文件夹</p>
        <p className="mt-1 text-xs text-slate-500">上传目标会跟随当前选中的文件夹。</p>
      </div>
    );
  }

  return (
    <div key={department.key} className="kb-fade-in mx-auto flex h-full w-full max-w-7xl flex-col px-6 py-6">
      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{department.name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {department.files.length} 个文件 · {department.chunk_count} 个片段
          </p>
        </div>
        <Button variant="secondary" disabled={busy !== null} onClick={onIndex}>
          {busy === 'index' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {busy === 'index' ? '索引中...' : '重建此文件夹索引'}
        </Button>
      </header>

      <FileUploader
        config={config}
        folderName={department.name}
        disabled={busy !== null}
        dragging={dragging}
        onFiles={onFiles}
        onDragging={onDragging}
      />

      {selectedFiles.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2">
          <span className="text-xs text-slate-400">已选 {selectedFiles.length} 个文件</span>
          <div className="flex gap-2">
            <Button variant="secondary" className="h-8 px-2 text-xs" disabled={busy !== null} onClick={onBatchRetry}>
              <RotateCw className="h-3.5 w-3.5" />
              批量重新索引
            </Button>
            <Button variant="danger" className="h-8 px-2 text-xs" disabled={busy !== null} onClick={onBatchDelete}>
              <Trash2 className="h-3.5 w-3.5" />
              批量删除
            </Button>
          </div>
        </div>
      )}

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
        {busy === 'upload' ? (
          <div className="space-y-2">
            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-orange-500" />
            </div>
            <div className="h-12 animate-pulse rounded-lg bg-slate-800" />
            <div className="h-12 animate-pulse rounded-lg bg-slate-800" />
          </div>
        ) : (
          <FileList
            files={department.files}
            selected={selectedFiles}
            department={department.key}
            onToggle={onToggleFile}
            onToggleAll={onToggleAll}
            onPreview={onPreview}
            onDelete={onDeleteFile}
            onRetry={onRetryFile}
            onDragStart={onDragStart}
          />
        )}
      </div>
    </div>
  );
}
