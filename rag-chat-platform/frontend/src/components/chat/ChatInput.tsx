import { Send, Square } from 'lucide-react';
import { useState } from 'react';

interface Props {
  disabled?: boolean;
  loading: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function ChatInput({ disabled, loading, onSend, onStop }: Props) {
  const [draft, setDraft] = useState('');

  const submit = () => {
    const text = draft.trim();
    if (!text || loading || disabled) return;
    onSend(text);
    setDraft('');
  };

  return (
    <div className="sticky bottom-0 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent px-4 pt-4 pb-6">
      <form
        className="mx-auto max-w-3xl rounded-2xl border border-slate-300 bg-white shadow-lg transition-all focus-within:ring-2 focus-within:ring-orange-500"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          value={draft}
          rows={2}
          maxLength={4000}
          placeholder={disabled ? '请先在左侧保存 API Key' : '问一个知识库里可能有答案的问题'}
          aria-label="输入问题"
          className="w-full resize-none border-0 bg-transparent p-4 text-sm outline-none"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="flex items-center justify-between px-3 pb-3">
          <span className="text-xs text-slate-400">{draft.length}/4000</span>
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
              disabled={disabled || !draft.trim()}
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
