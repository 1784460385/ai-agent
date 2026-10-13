import { Button } from '../ui/Button';

interface Props {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  confirmText?: string;
  confirmValue: string;
  busy?: boolean;
  onConfirmValueChange: (value: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}

export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel = '删除',
  confirmText,
  confirmValue,
  busy,
  onConfirmValueChange,
  onClose,
  onConfirm,
}: Props) {
  if (!open) return null;
  const canConfirm = !confirmText || confirmValue.trim() === confirmText;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/70 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl"
      >
        <h2 id="confirm-modal-title" className="text-lg font-semibold text-slate-100">
          {title}
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
        {confirmText && (
          <>
            <label className="mt-4 mb-1 block text-xs text-slate-500" htmlFor="confirm-folder-name">
              请输入「{confirmText}」以确认
            </label>
            <input
              id="confirm-folder-name"
              value={confirmValue}
              autoFocus
              aria-label="输入名称确认删除"
              onChange={(event) => onConfirmValueChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && canConfirm) {
                  event.preventDefault();
                  onConfirm();
                }
              }}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:ring-2 focus:ring-orange-500"
            />
          </>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={!canConfirm || busy}>
            {busy ? '处理中…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
