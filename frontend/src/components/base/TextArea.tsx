import { TextareaHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/utils';

export interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const textareaId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={textareaId}
            className="block text-sm font-medium text-ink/70 mb-1.5"
          >
            {label}
          </label>
        )}
        <textarea
          id={textareaId}
          className={cn(
            'flex min-h-[80px] w-full rounded-xl border border-line bg-white px-3.5 py-2 text-sm text-ink transition-colors',
            'placeholder:text-ink/35',
            'focus:outline-none focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40',
            'disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-ink-800/[0.03]',
            error && 'border-red-500 focus:ring-red-500/50',
            className
          )}
          ref={ref}
          {...props}
        />
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      </div>
    );
  }
);

TextArea.displayName = 'TextArea';

export { TextArea };

