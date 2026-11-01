import { ButtonHTMLAttributes, forwardRef } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-full font-medium tracking-tight transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        primary: 'bg-ink text-white hover:bg-ink-700 focus-visible:ring-accent-deep',
        secondary: 'bg-ink-800/5 text-ink hover:bg-ink-800/10 focus-visible:ring-ink-600',
        outline: 'border border-line text-ink bg-white hover:bg-ink-800/[0.04] hover:border-ink-600/30 focus-visible:ring-accent-deep',
        ghost: 'text-ink/70 hover:bg-ink-800/[0.06] hover:text-ink focus-visible:ring-ink-600',
        accent: 'bg-accent-deep text-white hover:brightness-110 focus-visible:ring-accent-deep',
        danger: 'bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-600',
      },
      size: {
        sm: 'h-9 px-4 text-sm',
        md: 'h-10 px-5 text-sm',
        lg: 'h-12 px-7 text-base',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <div className="flex items-center gap-2">
            <svg
              className="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            {children}
          </div>
        ) : (
          children
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { Button, buttonVariants };

