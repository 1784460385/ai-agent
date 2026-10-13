import { Paperclip, Send, Square, X } from 'lucide-react';
import { useRef, useState } from 'react';

const ACCEPT = '.pdf,.docx,.doc,.xlsx,.xls,.pptx,.md,.markdown,.txt,.html,.htm,.csv,.json,.ipynb,.jpg,.jpeg,.png,.gif,.webp';
const MAX_FILES = 3;

interface Props {
  disabled?: boolean;
  loading: boolean;
  onSend: (text: string, files: File[]) => void;
  onStop: () => void;
}

export function ChatInput({ disabled, loading, onSend, onStop }: Props) {
  const [draft, setDraft] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [hint, setHint] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = (list: FileList | null) => {
    if (!list?.length) return;
    const next = [...files];
    for (const file of Array.from(list)) {
      if (next.length >= MAX_FILES) {
        setHint(`一次最多 ${MAX_FILES} 个附件`);
        break;
      }
      if (next.some((item) => item.name === file.name && item.size === file.size)) continue;
      next.push(file);
    }
    setFiles(next);
    if (inputRef.current) inputRef.current.value = '';
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
      >
        {!!files.length && (
          <ul className="flex flex-wrap gap-2 px-4 pt-3">
            {files.map((file) => (
              <li key={`${file.name}-${file.size}`} className="flex items-center gap-1 rounded-full bg-orange-50 px-2 py-1 text-xs text-orange-700">
                <span className="max-w-40 truncate">{file.name}</span>
                <button
                  type="button"
                  aria-label={`移除 ${file.name}`}
                  className="rounded-full p-0.5 hover:bg-orange-100"
                  onClick={() => setFiles((current) => current.filter((item) => item !== file))}
                >
                  <X className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        <textarea
          value={draft}
          rows={4}
          maxLength={4000}
          placeholder={disabled ? '请先前往模型配置添加 API Key' : '问一个知识库里可能有答案的问题'}
          aria-label="输入问题"
          className="w-full resize-none border-0 bg-transparent p-4 text-base outline-none"
          onChange={(event) => setDraft(event.target.value)}
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
