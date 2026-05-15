import React from 'react';
import { cn } from '../../lib/utils';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 disabled:pointer-events-none disabled:opacity-50',
          {
            'bg-zinc-900 text-zinc-50 hover:bg-zinc-900/90': variant === 'primary',
            'bg-zinc-100 text-zinc-900 hover:bg-zinc-100/80': variant === 'secondary',
            'border border-zinc-200 bg-white hover:bg-zinc-100 hover:text-zinc-900': variant === 'outline',
            'hover:bg-zinc-100 hover:text-zinc-900': variant === 'ghost',
            'bg-red-500 text-zinc-50 hover:bg-red-500/90': variant === 'danger',
            'h-9 px-3': size === 'sm',
            'h-10 px-4 py-2': size === 'md',
            'h-11 rounded-md px-8': size === 'lg',
          },
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = 'Button';
