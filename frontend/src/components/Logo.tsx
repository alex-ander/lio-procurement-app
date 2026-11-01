/* eslint-disable @next/next/no-img-element */
import { cn } from '@/lib/utils';

interface LogoProps {
  /** Use "light" (white logo) on dark backgrounds, "dark" (black logo) on light. */
  variant?: 'light' | 'dark';
  className?: string;
}

/** The Lio brand logo (mark + wordmark). */
export function Logo({ variant = 'dark', className }: LogoProps) {
  const src = variant === 'light' ? '/logo-white.png' : '/logo-black.png';
  return (
    <img
      src={src}
      alt="Lio"
      className={cn('h-8 w-auto select-none', className)}
      draggable={false}
    />
  );
}
