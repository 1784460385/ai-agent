import { Menu, PanelLeft } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import {
  createFolder,
  deleteDocument,
  deleteFolder,
  fetchConfig,
  listDepartments,
  moveDocument,
  rebuildIndex,
  renameFolder,
  retryParse,
  uploadDocument,
  type AppConfig,
  type DepartmentInfo,
} from '../../api/client';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { MobileDrawer } from '../layout/MobileDrawer';
import { ConfirmModal } from './ConfirmModal';
import { FilePreviewDrawer } from './FilePreviewDrawer';
import { FolderDetail } from './FolderDetail';
import { FolderSidebar } from './FolderSidebar';

const SELECTED_KEY = 'kb-selected-folder';

export function KnowledgePanel() {
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const isWide = useMediaQuery('(min-width: 1280px)');
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [selectedKey, setSelectedKey] = useState(() => sessionStorage.getItem(SELECTED_KEY) || '');
  const [busy, setBusy] = useState<'upload' | 'index' | null>(null);
  const [dragging, setDragging] = useState(false);
  const [dropTarget, setDropTarget] = useState('');
  const [navOpen, setNavOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<{ key: string; name: string } | null>(null);
  const [confirmValue, setConfirmValue] = useState('');
  const [previewName, setPreviewName] = useState('');

  const selected = departments.find((item) => item.key === selectedKey);
  const collapsed = isDesktop && !isWide;

  const refresh = useCallback(async () => {
    const data = await listDepartments();
    setDepartments(data);
    setSelectedKey((current) => {
      const next = data.some((item) => item.key === current) ? current : data[0]?.key || '';
      if (next) sessionStorage.setItem(SELECTED_KEY, next);
      else sessionStorage.removeItem(SELECTED_KEY);
      return next;
    });
  }, []);

  useEffect(() => {
    refresh().catch(() => setError('后端未连接。请先启动 http://127.0.0.1:8000'));
    fetchConfig().then(setConfig).catch(() => undefined);
  }, [refresh]);

  const parsing = departments.some((dept) => dept.files.some((file) => file.parse_status === 'parsing'));

  useEffect(() => {
    if (!parsing) return undefined;
    const timer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [parsing, refresh]);

  useEffect(() => {
    setSelectedFiles([]);
  }, [selectedKey]);

  const selectFolder = (key: string) => {
    setSelectedKey(key);
    sessionStorage.setItem(SELECTED_KEY, key);
    setNavOpen(false);
    setError('');
  };

  const uploadFiles = async (files: File[]) => {
    const fallback = [
      '.pdf',
      '.docx',
      '.doc',
      '.xlsx',
      '.xls',
      '.pptx',
      '.md',
      '.markdown',
      '.txt',
      '.html',
      '.htm',
      '.csv',
      '.json',
      '.ipynb',
      '.jpg',
      '.jpeg',
      '.png',
      '.webp',
      '.bmp',
      '.tif',
      '.tiff',
    ];
    const allowed = new Set((config?.formats ?? fallback.map((ext) => ({ ext }))).map((item) => item.ext.toLowerCase()));
    const accepted = files.filter((file) => allowed.has(`.${file.name.split('.').pop()?.toLowerCase()}`));
    const rejected = files.filter((file) => !accepted.includes(file));
    if (!selectedKey) {
      setError('请先在左侧选择或新建文件夹');
      return;
    }
    if (!accepted.length) {
      setError(rejected.length ? '不支持的文件格式' : '请选择文件');
      return;
    }
    setBusy('upload');
    setError('');
    setMessage('');
    try {
      for (const file of accepted) {
        await uploadDocument(file, selectedKey);
      }
      await refresh();
      setMessage('正在解析并建立索引，列表会自动更新');
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setBusy(null);
    }
  };

  const runIndex = async (department?: string) => {
    setBusy('index');
    setError('');
    setMessage(department ? '正在重建此文件夹索引…' : '正在重建全部文件夹索引。模型已在本机时通常很快。');
    try {
      const result = await rebuildIndex(department);
      await refresh();
      if (result.status === 'ok') {
        setMessage(`索引完成，共 ${result.chunks_indexed ?? 0} 个片段`);
      } else {
        setMessage(result.message || '该部门没有可索引的文档');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '索引失败');
      setMessage('');
    } finally {
      setBusy(null);
    }
  };

  const retryFile = async (department: string, filename: string) => {
    setError('');
    try {
      await retryParse(department, filename);
      await refresh();
      setMessage('正在重新解析');
    } catch (err) {
      setError(err instanceof Error ? err.message : '重试失败');
    }
  };

  const removeFile = async (department: string, filename: string) => {
    if (!window.confirm(`删除 ${filename}？删除后需要重建该文件夹索引。`)) return;
    setError('');
    try {
      await deleteDocument(department, filename);
      await refresh();
      setSelectedFiles((current) => current.filter((item) => item !== filename));
      setMessage('文件已删除，请重建对应文件夹索引');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const addFolder = async (name: string) => {
    setError('');
    try {
      const created = await createFolder(name);
      await refresh();
      selectFolder(created.key);
      setMessage(`已新建文件夹「${created.name}」，可以把文件导入这里`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法新建文件夹');
    }
  };

  const changeFolderName = async (folderKey: string, name: string) => {
    setError('');
    try {
      const updated = await renameFolder(folderKey, name);
      await refresh();
      setMessage(`已重命名为「${updated.name}」`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法重命名文件夹');
    }
  };

  const confirmRemoveFolder = async () => {
    if (!deleteTarget) return;
    setError('');
    try {
      await deleteFolder(deleteTarget.key);
      setDeleteTarget(null);
      setConfirmValue('');
      await refresh();
      setMessage(`已删除文件夹「${deleteTarget.name}」`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法删除文件夹');
    }
  };

  const handleFileDrop = async (targetKey: string, payload: string) => {
    if (!payload.startsWith('kb-file:')) return;
    const rest = payload.slice('kb-file:'.length);
    const separator = rest.indexOf(':');
    const source = rest.slice(0, separator);
    const filename = rest.slice(separator + 1);
    if (!source || !filename || source === targetKey) return;
    setError('');
    try {
      await moveDocument(source, filename, targetKey);
      await refresh();
      setMessage(`已将「${filename}」移动到目标文件夹，请重建相关文件夹索引`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '移动失败');
    }
  };

  const batchDelete = async () => {
    if (!selected || !selectedFiles.length) return;
    if (!window.confirm(`删除选中的 ${selectedFiles.length} 个文件？删除后需要重建该文件夹索引。`)) return;
    setError('');
    try {
      for (const filename of selectedFiles) {
        await deleteDocument(selected.key, filename);
      }
      await refresh();
      setSelectedFiles([]);
      setMessage('文件已删除，请重建对应文件夹索引');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const batchRetry = async () => {
    if (!selected || !selectedFiles.length) return;
    setError('');
    try {
      for (const filename of selectedFiles) {
        await retryParse(selected.key, filename);
      }
      await refresh();
      setMessage('正在重新解析选中文件');
    } catch (err) {
      setError(err instanceof Error ? err.message : '重试失败');
    }
  };

  const sidebarProps = {
    departments,
    selectedKey,
    busy,
    dropTarget,
    onSelect: selectFolder,
    onCreate: addFolder,
    onRename: changeFolderName,
    onDelete: (key: string, name: string) => {
      setDeleteTarget({ key, name });
      setConfirmValue('');
    },
    onRebuildAll: () => void runIndex(),
    onFileDrop: (key: string, payload: string) => void handleFileDrop(key, payload),
    onDropTarget: setDropTarget,
  };

  return (
    <section className="flex h-full min-h-0 overflow-hidden bg-slate-950 text-slate-100">
      <aside className={`hidden h-full shrink-0 flex-col border-r border-slate-800 lg:flex ${collapsed ? 'w-16' : 'w-72 xl:w-80'}`}>
        <FolderSidebar {...sidebarProps} collapsed={collapsed} />
      </aside>
      <MobileDrawer open={navOpen && !isDesktop} onClose={() => setNavOpen(false)}>
        <div className="h-full w-80 max-w-[85vw] border-r border-slate-800">
          <FolderSidebar {...sidebarProps} collapsed={false} />
        </div>
      </MobileDrawer>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3 lg:hidden">
          <button
            type="button"
            aria-label="打开知识库导航"
            className="rounded-lg p-2 text-slate-300 hover:bg-slate-800"
            onClick={() => setNavOpen(true)}
          >
            <Menu className="h-5 w-5" />
          </button>
          <PanelLeft className="h-4 w-4 text-slate-500" />
          <span className="truncate text-sm font-semibold text-slate-100">{selected?.name || '知识库'}</span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <FolderDetail
            department={selected}
            config={config}
            busy={busy}
            dragging={dragging}
            selectedFiles={selectedFiles}
            onDragging={setDragging}
            onFiles={(files) => void uploadFiles(files)}
            onIndex={() => void runIndex(selected?.key)}
            onToggleFile={(filename) =>
              setSelectedFiles((current) => (current.includes(filename) ? current.filter((item) => item !== filename) : [...current, filename]))
            }
            onToggleAll={() =>
              setSelectedFiles((current) => (selected && current.length === selected.files.length ? [] : selected?.files.map((file) => file.name) || []))
            }
            onPreview={setPreviewName}
            onDeleteFile={(filename) => selected && void removeFile(selected.key, filename)}
            onRetryFile={(filename) => selected && void retryFile(selected.key, filename)}
            onBatchDelete={() => void batchDelete()}
            onBatchRetry={() => void batchRetry()}
            onDragStart={() => undefined}
          />
          {(message || error) && (
            <div className="mx-auto w-full max-w-7xl px-6 pb-6">
              {message && <p className="text-xs leading-5 text-slate-400">{message}</p>}
              {error && <p className="text-xs leading-5 text-red-300">{error}</p>}
            </div>
          )}
        </div>
      </div>

      <ConfirmModal
        open={Boolean(deleteTarget)}
        title={`删除文件夹「${deleteTarget?.name || ''}」`}
        description="将同时删除该文件夹下的全部文件，此操作不可恢复。"
        confirmText={deleteTarget?.name}
        confirmValue={confirmValue}
        onConfirmValueChange={setConfirmValue}
        onClose={() => {
          setDeleteTarget(null);
          setConfirmValue('');
        }}
        onConfirm={() => void confirmRemoveFolder()}
      />

      {previewName && selected && (
        <FilePreviewDrawer
          department={selected.key}
          filename={previewName}
          size={selected.files.find((file) => file.name === previewName)?.size ?? 0}
          onClose={() => setPreviewName('')}
        />
      )}
    </section>
  );
}
