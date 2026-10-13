import { FileText, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fetchDocumentContent, previewDocument } from '../../api/client';
import { formatSize } from './status';

interface Props {
  department: string;
  filename: string;
  size: number;
  onClose: () => void;
}

export function FilePreviewDrawer({ department, filename, size, onClose }: Props) {
  const [text, setText] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const isPdf = filename.toLowerCase().endsWith('.pdf');

  useEffect(() => {
    let revoked = '';
    let active = true;
    setLoading(true);
    setError('');
    setText('');
    setPdfUrl('');

    const load = async () => {
      try {
        if (isPdf) {
          const blob = await fetchDocumentContent(department, filename);
          if (!active) return;
          const url = URL.createObjectURL(blob);
          revoked = url;
          setPdfUrl(url);
        } else {
          const result = await previewDocument(department, filename);
          if (!active) return;
          setText(result.preview);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : '无法预览此文件');
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    return () => {
      active = false;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [department, filename, isPdf]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button type="button" aria-label="关闭预览" className="absolute inset-0 bg-slate-950/50" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-100">{filename}</h2>
            <p className="mt-1 text-xs text-slate-500">{formatSize(size)}</p>
          </div>
          <button
            type="button"
            aria-label="关闭文件预览"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {loading && (
            <div className="space-y-3">
              <div className="h-4 animate-pulse rounded bg-slate-800" />
              <div className="h-4 w-5/6 animate-pulse rounded bg-slate-800" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-slate-800" />
            </div>
          )}
          {!loading && error && <p className="text-sm text-red-300">{error}</p>}
          {!loading && !error && pdfUrl && (
            <iframe title={`${filename} 预览`} src={pdfUrl} className="h-full min-h-[32rem] w-full rounded-lg bg-white" />
          )}
          {!loading && !error && !pdfUrl && text && (
            <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{text}</pre>
          )}
          {!loading && !error && !pdfUrl && !text && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <FileText className="mb-3 h-8 w-8 text-slate-600" />
              <p className="text-sm text-slate-400">无法提取正文预览，可查看文件名称与大小。</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
