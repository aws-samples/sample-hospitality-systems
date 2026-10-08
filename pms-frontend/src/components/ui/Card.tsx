import { HTMLAttributes, ReactNode } from 'react';

type CardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  padding?: 'none' | 'sm' | 'md' | 'lg';
};

const PAD = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

export function Card({ children, padding = 'none', className = '', ...rest }: CardProps) {
  return (
    <div
      className={`rounded-xl border border-neutral-200 bg-white shadow-xs ${PAD[padding]} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

type CardHeaderProps = HTMLAttributes<HTMLDivElement> & {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
};

export function CardHeader({ title, subtitle, actions, className = '', ...rest }: CardHeaderProps) {
  return (
    <div
      className={`flex items-start justify-between gap-4 px-6 py-4 border-b border-neutral-200 ${className}`}
      {...rest}
    >
      <div className="min-w-0">
        <h2 className="font-display text-lg font-semibold text-neutral-900">{title}</h2>
        {subtitle && <p className="text-sm text-neutral-500 mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

export function CardBody({ children, className = '', padding = 'md', ...rest }: CardProps) {
  return (
    <div className={`${PAD[padding]} ${className}`} {...rest}>
      {children}
    </div>
  );
}
