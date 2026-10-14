import { FileText, Paperclip, Send, Square, X } from 'lucide-react';
import { useEffect, useRef, useState, type ClipboardEvent } from 'react';

const ACCEPT = '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.md,.markdown,.txt,.html,.htm,.csv,.json,.ipynb,.jpg,.jpeg,.png,.gif,.webp';
const ACCEPT_SET = new Set(ACCEPT.split(',').map((item) => item.trim().toLowerCase()));
const MIME_EXT: Record<string, string> = {
  'image/png': '.png',
  'image/jpeg': '.jpg',
  'image/jpg': '.jpg',
  'image/gif': '.gif',
  'image/webp': '.webp',
  'application/pdf': '.pdf',
};
const IMAGE_EXT = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp']);
const MAX_FILES = 3;

interface Props {
  disabled?: boolean;
  loading: boolean;
  onSend: (text: string, files: File[]) => void;
  onStop: () => void;
}

function fileExtension(file: File) {
  const fromName = file.name.includes('.') ? `.${file.name.split('.').pop()!.toLowerCase()}` : '';
  if (fromName && ACCEPT_SET.has(fromName)) return fromName;
  return MIME_EXT[file.type] || fromName;
}

function isImageFile(file: File) {
  if (file.type.startsWith('image/')) return true;
  return IMAGE_EXT.has(fileExtension(file));
}

function normalizePastedFile(file: File, index: number) {
  const ext = fileExtension(file);
  if (!ext || !ACCEPT_SET.has(ext)) return null;
  const base = file.name?.trim();
  const needsName = !base || base === 'image.png' || base === 'blob' || !base.includes('.');
  if (!needsName) return file;
  return new File([file], `粘贴-${Date.now()}-${index + 1}${ext}`, {
    type: file.type || undefined,
    lastModified: file.lastModified,
  });
}

function AttachmentChip({
  file,
  previewUrl,
  onRemove,
}: {
  file: File;
  previewUrl?: string;
  onRemove: () => void;
}) {
  const image = isImageFile(file);
  const ext = (fileExtension(file) || '').replace('.', '').toUpperCase() || 'FILE';

  return (
    <li className="relative">
      {image && previewUrl ? (
        <div className="relative h-16 w-16 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sm">
          <img src={previewUrl} alt={file.name} className="h-full w-full object-cover" />
        </div>
      ) : (
        <div className="flex h-16 min-w-16 max-w-36 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-2.5 shadow-sm">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-orange-100 text-orange-600">
            <FileText className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-slate-700" title={file.name}>
              {file.name}
            </span>
            <span className="block text-[10px] uppercase tracking-wide text-slate-400">{ext}</span>
          </span>
        </div>
      )}
      <button
        type="button"
        aria-label={`移除 ${file.name}`}
        className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-100 hover:text-slate-800"
        onClick={onRemove}
      >
        <X className="h-3 w-3" />
      </button>
    </li>
  );
}

export function ChatInput({ disabled, loading, onSend, onStop }: Props) {
  const [draft, setDraft] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [hint, setHint] = useState('');
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const urls = files.map((file) => (isImageFile(file) ? URL.createObjectURL(file) : ''));
    setPreviewUrls(urls);
    return () => {
      for (const url of urls) {
        if (url) URL.revokeObjectURL(url);
      }
    };
  }, [files]);

  const addFiles = (list: FileList | File[] | null) => {
    if (!list?.length) return;
    const next = [...files];
    let rejected = false;
    for (const raw of Array.from(list)) {
      const file = normalizePastedFile(raw, next.length);
      if (!file) {
        rejected = true;
        continue;
      }
      if (next.length >= MAX_FILES) {
        setHint(`一次最多 ${MAX_FILES} 个附件`);
        break;
      }
      if (next.some((item) => item.name === file.name && item.size === file.size)) continue;
      next.push(file);
    }
    setFiles(next);
    if (rejected && next.length === files.length) {
      setHint('仅支持文档或图片附件');
    } else if (!rejected) {
      setHint('');
    }
    if (inputRef.current) inputRef.current.value = '';
  };

  const handlePaste = (event: ClipboardEvent) => {
    if (disabled || loading) return;
    const { clipboardData } = event;
    if (!clipboardData) return;

    const collected: File[] = [];
    if (clipboardData.files?.length) {
      collected.push(...Array.from(clipboardData.files));
    } else {
      for (const item of Array.from(clipboardData.items || [])) {
        if (item.kind !== 'file') continue;
        const file = item.getAsFile();
        if (file) collected.push(file);
      }
    }
    if (!collected.length) return;

    const plain = clipboardData.getData('text/plain');
    if (!plain) event.preventDefault();
    event.stopPropagation();
    addFiles(collected);
  };

  const submit = () => {
    const text = draft.trim();
    if (loading || disabled || (!text && !files.length)) return;
    onSend(text, files);
    setDraft('');
    setFiles([]);
    setHint('');
  };

  return (
    <div className="sticky bottom-0 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent px-4 pt-4 pb-6 md:px-8">
      <form
        className="mx-auto w-full max-w-6xl rounded-2xl border border-slate-300 bg-white shadow-lg transition-all focus-within:ring-2 focus-within:ring-orange-500"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        onPaste={handlePaste}
      >
        {!!files.length && (
          <ul className="flex flex-wrap gap-3 px-4 pt-3">
            {files.map((file, index) => (
              <AttachmentChip
                key={`${file.name}-${file.size}-${file.lastModified}`}
                file={file}
                previewUrl={previewUrls[index]}
                onRemove={() => setFiles((current) => current.filter((item) => item !== file))}
              />
            ))}
          </ul>
        )}
        <textarea
          value={draft}
          rows={4}
          maxLength={4000}
          placeholder={disabled ? '请先前往模型配置添加 API Key' : '问一个知识库里可能有答案的问题，也可粘贴图片或文件'}
          aria-label="输入问题"
          className="w-full resize-none border-0 bg-transparent p-4 text-base outline-none"
          onChange={(event) => setDraft(event.target.value)}
          onPaste={handlePaste}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="flex items-center justify-between px-3 pb-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="添加附件"
              disabled={disabled || loading}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-50"
              onClick={() => inputRef.current?.click()}
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input ref={inputRef} type="file" accept={ACCEPT} multiple className="hidden" onChange={(event) => addFiles(event.target.files)} />
            <span className="text-xs text-slate-400">{draft.length}/4000</span>
            {hint && <span className="text-xs text-red-500">{hint}</span>}
          </div>
          {loading ? (
            <button
              type="button"
              aria-label="停止生成"
              className="rounded-xl bg-red-600 p-2 text-white transition-transform hover:scale-105 active:scale-95"
              onClick={onStop}
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              type="submit"
              aria-label="发送"
              disabled={disabled || (!draft.trim() && !files.length)}
              className="rounded-xl bg-orange-500 p-2 text-white transition-transform hover:scale-105 hover:bg-orange-600 active:scale-95 disabled:opacity-50 disabled:hover:scale-100"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
