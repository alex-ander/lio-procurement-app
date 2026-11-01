import { InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-ink/70 mb-1.5"
          >
            {label}
          </label>
        )}
        <input
          id={inputId}
          className={cn(
            'flex h-11 w-full rounded-xl border border-line bg-white px-3.5 py-2 text-sm text-ink transition-colors',
            'file:border-0 file:bg-transparent file:text-sm file:font-medium',
            'placeholder:text-ink/35',
            'focus:outline-none focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40',
            'disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-ink-800/[0.03]',
            error && 'border-red-500 focus:ring-red-500/50',
            className
          )}
          ref={ref}
          {...props}
        />
        {error && <p className="mt-1.5 text-sm text-red-600">{error}</p>}
        {!error && helperText && (
          <p className="mt-1.5 text-sm text-ink/45">{helperText}</p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input };

