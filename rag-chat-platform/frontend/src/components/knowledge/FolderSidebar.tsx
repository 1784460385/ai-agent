import { Folder, Loader2, MoreVertical, Plus, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type DragEvent } from 'react';
import type { DepartmentInfo } from '../../api/client';
import { Button } from '../ui/Button';
import { folderIndexStatus } from './status';

interface Props {
  departments: DepartmentInfo[];
  selectedKey: string;
  collapsed?: boolean;
  busy: 'upload' | 'index' | null;
  dropTarget: string;
  onSelect: (key: string) => void;
  onCreate: (name: string) => Promise<void>;
  onRename: (key: string, name: string) => Promise<void>;
  onDelete: (key: string, name: string) => void;
  onRebuildAll: () => void;
  onFileDrop: (targetKey: string, payload: string) => void;
  onDropTarget: (key: string) => void;
}

const badgeClass: Record<string, string> = {
  indexed: 'bg-emerald-500/15 text-emerald-400',
  pending: 'bg-slate-700 text-slate-400',
  indexing: 'bg-amber-500/15 text-amber-300',
};

const badgeLabel: Record<string, string> = {
  indexed: '已索引',
  pending: '未索引',
  indexing: '索引中',
};

export function FolderSidebar({
  departments,
  selectedKey,
  collapsed,
  busy,
  dropTarget,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onRebuildAll,
  onFileDrop,
  onDropTarget,
}: Props) {
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [menuKey, setMenuKey] = useState('');
  const [renameKey, setRenameKey] = useState('');
  const [renameValue, setRenameValue] = useState('');

  const visible = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return departments;
    return departments.filter((item) => item.name.toLowerCase().includes(text) || item.key.toLowerCase().includes(text));
  }, [departments, query]);

  useEffect(() => {
    if (!menuKey) return undefined;
    const close = () => setMenuKey('');
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [menuKey]);

  const submitCreate = async () => {
    const name = folderName.trim();
    if (!name) return;
    await onCreate(name);
    setFolderName('');
    setCreating(false);
  };

  const submitRename = async () => {
    const name = renameValue.trim();
    if (!name || !renameKey) return;
    await onRename(renameKey, name);
    setRenameKey('');
    setRenameValue('');
  };

  const acceptFileDrop = (event: DragEvent, key: string) => {
    event.preventDefault();
    onDropTarget('');
    onFileDrop(key, event.dataTransfer.getData('text/plain'));
  };

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <div className={`border-b border-slate-800 ${collapsed ? 'p-2' : 'p-4'}`}>
        {collapsed ? (
          <div className="relative">
            <button
              type="button"
              aria-label="新建文件夹"
              className="grid h-10 w-full place-items-center rounded-lg text-orange-400 hover:bg-slate-800"
              onClick={() => setCreating((value) => !value)}
            >
              <Plus className="h-4 w-4" />
            </button>
            {creating && (
              <input
                autoFocus
                value={folderName}
                placeholder="新建文件夹"
                aria-label="新建文件夹名称"
                onChange={(event) => setFolderName(event.target.value)}
                onBlur={() => {
                  if (!folderName.trim()) setCreating(false);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    void submitCreate();
                  }
                  if (event.key === 'Escape') {
                    setCreating(false);
                    setFolderName('');
                  }
                }}
                className="absolute top-12 left-0 z-20 w-56 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-orange-500"
              />
            )}
          </div>
        ) : creating ? (
          <input
            autoFocus
            value={folderName}
            placeholder="输入文件夹名称，回车确认"
            aria-label="新建文件夹名称"
            onChange={(event) => setFolderName(event.target.value)}
            onBlur={() => {
              if (!folderName.trim()) setCreating(false);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void submitCreate();
              }
              if (event.key === 'Escape') {
                setCreating(false);
                setFolderName('');
              }
            }}
            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-orange-500"
          />
        ) : (
          <Button className="w-full" onClick={() => setCreating(true)} disabled={busy !== null}>
            <Plus className="h-4 w-4" />
            新建文件夹
          </Button>
        )}
        {!collapsed && (
          <label className="relative mt-3 block">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              value={query}
              placeholder="搜索文件夹..."
              aria-label="搜索文件夹"
              onChange={(event) => setQuery(event.target.value)}
              className="w-full rounded-lg border border-slate-800 bg-slate-900 py-2 pr-3 pl-9 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-orange-500"
            />
          </label>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-2" aria-label="知识库文件夹">
        {visible.length === 0 ? (
          <p className={`${collapsed ? 'px-1 text-center text-[10px]' : 'px-2 py-8 text-center text-sm'} text-slate-500`}>
            {departments.length === 0 ? '📁 还没有知识库目录，点击上方新建。' : '没有匹配的文件夹'}
          </p>
        ) : (
          visible.map((department) => {
            const selected = selectedKey === department.key;
            const status = folderIndexStatus(department);
            const renaming = renameKey === department.key;
            return (
              <div
                key={department.key}
                onDragOver={(event) => {
                  event.preventDefault();
                  onDropTarget(department.key);
                }}
                onDragLeave={() => onDropTarget('')}
                onDrop={(event) => acceptFileDrop(event, department.key)}
                className={`group relative mb-1 flex items-center justify-between rounded-lg p-3 transition-colors ${
                  selected ? 'border-l-2 border-orange-500 bg-slate-800' : 'border-l-2 border-transparent hover:bg-slate-800'
                } ${dropTarget === department.key ? 'bg-orange-500/10' : ''} ${collapsed ? 'justify-center px-2' : ''}`}
              >
                {renaming ? (
                  <input
                    autoFocus
                    value={renameValue}
                    aria-label={`重命名 ${department.name}`}
                    className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-orange-500"
                    onChange={(event) => setRenameValue(event.target.value)}
                    onBlur={() => void submitRename()}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void submitRename();
                      }
                      if (event.key === 'Escape') {
                        setRenameKey('');
                        setRenameValue('');
                      }
                    }}
                  />
                ) : (
                  <>
                    <button
                      type="button"
                      aria-current={selected ? 'page' : undefined}
                      aria-label={department.name}
                      title={department.name}
                      className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
                      onClick={() => onSelect(department.key)}
                      onContextMenu={(event) => {
                        event.preventDefault();
                        setMenuKey(department.key);
                      }}
                    >
                      <Folder className={`h-4 w-4 shrink-0 ${selected ? 'text-orange-500' : 'text-slate-400'}`} />
                      {!collapsed && (
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-slate-100">{department.name}</span>
                          <span className="flex items-center gap-2 text-xs text-slate-500">
                            {department.files.length} 个文件
                            <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${badgeClass[status]}`}>{badgeLabel[status]}</span>
                          </span>
                        </span>
                      )}
                    </button>
                    <button
                      type="button"
                      aria-label={`${department.name} 更多操作`}
                      className={`rounded p-1 text-slate-500 hover:bg-slate-700 hover:text-slate-200 ${
                        collapsed ? 'absolute top-1 right-0 opacity-0 group-hover:opacity-100' : 'opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100'
                      }`}
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuKey((current) => (current === department.key ? '' : department.key));
                      }}
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>
                  </>
                )}
                {menuKey === department.key && (
                  <div className="absolute top-10 right-2 z-10 w-28 rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-lg">
                    <button
                      type="button"
                      className="block w-full px-3 py-1.5 text-left text-sm text-slate-200 hover:bg-slate-800"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuKey('');
                        setRenameKey(department.key);
                        setRenameValue(department.name);
                      }}
                    >
                      重命名
                    </button>
                    <button
                      type="button"
                      className="block w-full px-3 py-1.5 text-left text-sm text-red-300 hover:bg-slate-800"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuKey('');
                        onDelete(department.key, department.name);
                      }}
                    >
                      删除
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </nav>

      <div className="border-t border-slate-800 p-3">
        <Button variant="secondary" className={`w-full ${collapsed ? 'px-0' : ''}`} disabled={busy !== null} onClick={onRebuildAll}>
          {busy === 'index' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {!collapsed && (busy === 'index' ? '索引中...' : '重建全部索引')}
        </Button>
      </div>
    </div>
  );
}
