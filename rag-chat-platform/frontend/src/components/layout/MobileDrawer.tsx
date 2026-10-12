import type { ReactNode } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function MobileDrawer({ open, onClose, children }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button type="button" aria-label="关闭菜单" className="absolute inset-0 bg-slate-900/50" onClick={onClose} />
      <div className="relative h-full w-80 max-w-[85vw] shadow-lg">{children}</div>
    </div>
  );
}
