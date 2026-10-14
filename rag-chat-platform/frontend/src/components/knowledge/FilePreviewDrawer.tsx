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
  const [imageUrl, setImageUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const lower = filename.toLowerCase();
  const isPdf = lower.endsWith('.pdf');
  const isImage = /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(lower);

  useEffect(() => {
    let revoked = '';
    let active = true;
    setLoading(true);
    setError('');
    setText('');
    setPdfUrl('');
    setImageUrl('');

    const load = async () => {
      try {
        if (isPdf) {
          const blob = await fetchDocumentContent(department, filename);
          if (!active) return;
          const url = URL.createObjectURL(blob);
          revoked = url;
          setPdfUrl(url);
        } else if (isImage) {
          const [blob, result] = await Promise.all([
            fetchDocumentContent(department, filename),
            previewDocument(department, filename),
          ]);
          if (!active) return;
          const url = URL.createObjectURL(blob);
          revoked = url;
          setImageUrl(url);
          setText(result.preview);
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
  }, [department, filename, isPdf, isImage]);

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
          {!loading && !error && imageUrl && (
            <div className="space-y-4">
              <img src={imageUrl} alt={filename} className="max-h-80 w-full rounded-lg object-contain bg-slate-900" />
              {text ? (
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">OCR 识别文本</p>
                  <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{text}</pre>
                </div>
              ) : (
                <p className="text-sm text-slate-500">尚未识别到文字，可重试解析。</p>
              )}
            </div>
          )}
          {!loading && !error && !pdfUrl && !imageUrl && text && (
            <pre className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{text}</pre>
          )}
          {!loading && !error && !pdfUrl && !imageUrl && !text && (
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
