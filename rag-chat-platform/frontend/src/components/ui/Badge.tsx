import type { ReactNode } from 'react';
import { cn } from '../../lib/utils';

export function Badge({
  children,
  className,
  dot,
}: {
  children: ReactNode;
  className?: string;
  dot?: 'on' | 'off';
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300',
        className
      )}
    >
      {dot && (
        <span className={cn('h-1.5 w-1.5 rounded-full', dot === 'on' ? 'bg-emerald-400' : 'bg-slate-500')} />
      )}
      {children}
    </span>
  );
}
