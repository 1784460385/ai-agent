import { useCallback, useEffect, useState } from 'react';
import { fetchStats, listDocuments, rebuildIndex, uploadDocument, type DocumentInfo } from '../api/client';

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function KnowledgeUpload() {
  const [files, setFiles] = useState<DocumentInfo[]>([]);
  const [chunks, setChunks] = useState<number | null>(null);
  const [busy, setBusy] = useState<'upload' | 'index' | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);

  const refresh = useCallback(async () => {
    const [docs, indexed] = await Promise.all([listDocuments(), fetchStats()]);
    setFiles(docs);
    setChunks(indexed);
  }, []);

  useEffect(() => {
    refresh().catch(() => {
      setError('后端未连接。请先启动 http://127.0.0.1:8000');
    });
  }, [refresh]);

  const uploadFiles = async (list: File[]) => {
    const accepted = list.filter((file) => /\.(pdf|md|markdown|txt)$/i.test(file.name));
    if (!accepted.length) {
      setError('仅支持 PDF、Markdown、TXT');
      return;
    }
    setBusy('upload');
    setError('');
    setMessage('');
    try {
      for (const file of accepted) {
        await uploadDocument(file);
      }
      await refresh();
      setMessage(`已上传 ${accepted.length} 个文件，请重建索引后生效`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setBusy(null);
    }
  };

  const handleIndex = async () => {
    setBusy('index');
    setError('');
    setMessage('正在索引。首次会下载约 2GB 的 Embedding 模型，进度显示在后端终端，请保持页面打开。');
    try {
      const result = await rebuildIndex();
      await refresh();
      if (result.status === 'ok') {
        setMessage(`索引完成，共 ${result.chunks_indexed ?? 0} 个片段`);
      } else {
        setMessage(result.message || '知识库为空');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '索引失败');
      setMessage('');
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>知识库</h2>
        <span className="pill">{chunks === null ? '—' : `${chunks} 片段`}</span>
      </div>
      <label
        className={dragging ? 'dropzone dragging' : 'dropzone'}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void uploadFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <input
          type="file"
          accept=".pdf,.md,.markdown,.txt,text/plain,application/pdf"
          multiple
          disabled={busy !== null}
          onChange={(event) => {
            const selected = event.target.files ? Array.from(event.target.files) : [];
            event.target.value = '';
            void uploadFiles(selected);
          }}
        />
        <strong>{busy === 'upload' ? '正在上传…' : '拖入或选择文档'}</strong>
        <span>PDF / Markdown / TXT，单个不超过 20MB</span>
      </label>
      <ul className="file-list">
        {files.length === 0 && <li className="muted">还没有文档</li>}
        {files.map((file) => (
          <li key={file.name}>
            <span>{file.name}</span>
            <em>{formatSize(file.size)}</em>
          </li>
        ))}
      </ul>
      <button type="button" className="btn btn-ghost" onClick={handleIndex} disabled={busy !== null}>
        {busy === 'index' ? '索引中…' : '重建索引'}
      </button>
      {message && <p className="hint">{message}</p>}
      {error && <p className="hint hint-error">{error}</p>}
    </section>
  );
}
