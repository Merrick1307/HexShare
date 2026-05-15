import React from 'react';
import { cn } from '../../lib/utils';

export type BadgeProps = React.ComponentProps<'div'> & {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'neutral';
};

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-950 focus:ring-offset-2',
        {
          'border-transparent bg-zinc-900 text-zinc-50': variant === 'default',
          'border-transparent bg-emerald-100 text-emerald-800': variant === 'success',
          'border-transparent bg-amber-100 text-amber-800': variant === 'warning',
          'border-transparent bg-red-100 text-red-800': variant === 'danger',
          'border-zinc-200 bg-zinc-100 text-zinc-900': variant === 'neutral',
        },
        className
      )}
      {...props}
    />
  );
}
