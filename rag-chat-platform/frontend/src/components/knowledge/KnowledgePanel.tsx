import { useCallback, useEffect, useState } from 'react';
import {
  createFolder,
  deleteDocument,
  deleteFolder,
  fetchConfig,
  listDepartments,
  rebuildIndex,
  retryParse,
  uploadDocument,
  type AppConfig,
  type DepartmentInfo,
} from '../../api/client';
import { Button } from '../ui/Button';
import { DepartmentGroup } from './DepartmentGroup';
import { FileUploader } from './FileUploader';

export function KnowledgePanel() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [departments, setDepartments] = useState<DepartmentInfo[]>([]);
  const [openKey, setOpenKey] = useState('finance');
  const [target, setTarget] = useState('finance');
  const [busy, setBusy] = useState<'upload' | 'index' | null>(null);
  const [dragging, setDragging] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    const data = await listDepartments();
    setDepartments(data);
    setTarget((current) => (data.some((item) => item.key === current) ? current : data[0]?.key || ''));
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

  const uploadFiles = async (files: File[]) => {
    const fallback = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.md', '.markdown', '.txt', '.html', '.htm', '.csv', '.json', '.ipynb'];
    const allowed = new Set((config?.formats ?? fallback.map((ext) => ({ ext }))).map((item) => item.ext.toLowerCase()));
    const accepted = files.filter((file) => allowed.has(`.${file.name.split('.').pop()?.toLowerCase()}`));
    const rejected = files.filter((file) => !accepted.includes(file));
    if (!target) {
      setError('请先新建一个文件夹');
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
        await uploadDocument(file, target);
      }
      await refresh();
      setOpenKey(target);
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
      setMessage('文件已删除，请重建对应文件夹索引');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const addFolder = async () => {
    const name = folderName.trim();
    if (!name) {
      setError('请输入文件夹名称');
      return;
    }
    setError('');
    try {
      const created = await createFolder(name);
      setFolderName('');
      setOpenKey(created.key);
      setTarget(created.key);
      await refresh();
      setMessage(`已新建文件夹「${created.name}」，可以把文件导入这里`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法新建文件夹');
    }
  };

  const removeFolder = async (folderKey: string, folderLabel: string) => {
    if (!window.confirm(`删除文件夹「${folderLabel}」及其全部文件？`)) return;
    setError('');
    try {
      await deleteFolder(folderKey);
      await refresh();
      setMessage(`已删除文件夹「${folderLabel}」`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法删除文件夹');
    }
  };

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-medium tracking-wider text-slate-400 uppercase">知识库</h2>
      <div className="flex gap-2">
        <input
          value={folderName}
          placeholder="新建文件夹"
          aria-label="新建文件夹"
          onChange={(event) => setFolderName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void addFolder();
            }
          }}
          className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-orange-500"
        />
        <Button className="shrink-0" onClick={() => void addFolder()} disabled={busy !== null}>
          新建
        </Button>
      </div>
      {departments.length === 0 ? (
        <p className="text-xs leading-5 text-slate-400">还没有文件夹。先新建一个，再把文档导入进去。</p>
      ) : (
        <FileUploader
        departments={departments}
        config={config}
        value={target}
        disabled={busy !== null}
        dragging={dragging}
        onChange={setTarget}
        onFiles={(files) => void uploadFiles(files)}
        onDragging={setDragging}
      />
      )}
      <div className="space-y-2">
        {departments.map((department) => (
          <DepartmentGroup
            key={department.key}
            department={department}
            open={openKey === department.key}
            busy={busy !== null}
            onToggle={() => setOpenKey((current) => (current === department.key ? '' : department.key))}
            onIndex={() => void runIndex(department.key)}
            onDelete={(filename) => void removeFile(department.key, filename)}
            onRetry={(filename) => void retryFile(department.key, filename)}
            onRemoveFolder={() => void removeFolder(department.key, department.name)}
          />
        ))}
      </div>
      <Button variant="secondary" className="w-full" disabled={busy !== null} onClick={() => void runIndex()}>
        {busy === 'index' ? '索引中…' : '重建全部索引'}
      </Button>
      {message && <p className="text-xs leading-5 text-slate-400">{message}</p>}
      {error && <p className="text-xs leading-5 text-red-300">{error}</p>}
    </section>
  );
}
