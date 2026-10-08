import { ButtonHTMLAttributes, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';

type Variant = 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger' | 'success';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-primary-600 text-white hover:bg-primary-700 focus:ring-primary-600/40 disabled:hover:bg-primary-600',
  accent:
    'bg-accent-500 text-white hover:bg-accent-600 focus:ring-accent-400/50 disabled:hover:bg-accent-500',
  secondary:
    'bg-white text-neutral-800 border border-neutral-300 hover:bg-neutral-50 focus:ring-primary-600/30 disabled:hover:bg-white',
  ghost:
    'bg-transparent text-neutral-700 hover:bg-neutral-100 focus:ring-primary-600/20 disabled:hover:bg-transparent',
  danger:
    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500/40 disabled:hover:bg-red-600',
  success:
    'bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-500/40 disabled:hover:bg-emerald-600',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  leftIcon,
  rightIcon,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      disabled={isDisabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition-colors focus:outline-hidden focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...rest}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : leftIcon ? (
        <span className="shrink-0">{leftIcon}</span>
      ) : null}
      {children}
      {!loading && rightIcon && <span className="shrink-0">{rightIcon}</span>}
    </button>
  );
}
