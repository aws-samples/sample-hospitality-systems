import { ReactNode } from 'react';

type BadgeVariant =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'
  | 'accent'
  | 'primary'
  // Room/operational statuses
  | 'available'
  | 'occupied'
  | 'dirty'
  | 'cleaning'
  | 'inspecting'
  | 'outOfOrder'
  // Loyalty tiers
  | 'standard'
  | 'silver'
  | 'gold'
  | 'diamond';

const VARIANTS: Record<BadgeVariant, string> = {
  neutral: 'bg-neutral-100 text-neutral-700 ring-neutral-200',
  info: 'bg-primary-50 text-primary-700 ring-primary-100',
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  warning: 'bg-amber-50 text-amber-800 ring-amber-100',
  danger: 'bg-red-50 text-red-700 ring-red-100',
  accent: 'bg-accent-50 text-accent-800 ring-accent-200',
  primary: 'bg-primary-600 text-white ring-primary-700',

  available: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  occupied: 'bg-primary-50 text-primary-700 ring-primary-100',
  dirty: 'bg-amber-50 text-amber-800 ring-amber-100',
  cleaning: 'bg-orange-50 text-orange-800 ring-orange-100',
  inspecting: 'bg-purple-50 text-purple-700 ring-purple-100',
  outOfOrder: 'bg-red-50 text-red-700 ring-red-100',

  standard: 'bg-neutral-100 text-neutral-600 ring-neutral-200',
  silver: 'bg-neutral-200 text-neutral-700 ring-neutral-300',
  gold: 'bg-accent-50 text-accent-800 ring-accent-200',
  diamond: 'bg-purple-50 text-purple-700 ring-purple-100',
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${VARIANTS[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

export function tierVariant(tier?: string): BadgeVariant {
  switch ((tier ?? '').toUpperCase()) {
    case 'DIAMOND':
      return 'diamond';
    case 'GOLD':
      return 'gold';
    case 'SILVER':
      return 'silver';
    default:
      return 'standard';
  }
}

export function reservationStatusVariant(status?: string): BadgeVariant {
  switch ((status ?? '').toUpperCase()) {
    case 'CHECKED_IN':
      return 'occupied';
    case 'CONFIRMED':
      return 'success';
    case 'CHECKED_OUT':
      return 'neutral';
    case 'CANCELLED':
    case 'NO_SHOW':
      return 'danger';
    default:
      return 'warning';
  }
}

export function folioStatusVariant(status?: string): BadgeVariant {
  switch ((status ?? '').toUpperCase()) {
    case 'PAID':
      return 'success';
    case 'OPEN':
      return 'info';
    case 'PENDING_PAYMENT':
      return 'warning';
    case 'VOID':
      return 'neutral';
    default:
      return 'danger';
  }
}

export function roomStatusVariant(status?: string): BadgeVariant {
  switch ((status ?? '').toUpperCase()) {
    case 'AVAILABLE':
      return 'available';
    case 'OCCUPIED':
      return 'occupied';
    case 'DIRTY':
      return 'dirty';
    case 'CLEANING':
      return 'cleaning';
    case 'INSPECTING':
      return 'inspecting';
    case 'OUT_OF_ORDER':
      return 'outOfOrder';
    default:
      return 'neutral';
  }
}

export function priorityVariant(priority?: string): BadgeVariant {
  switch ((priority ?? '').toUpperCase()) {
    case 'HIGH':
      return 'danger';
    case 'NORMAL':
      return 'neutral';
    case 'LOW':
      return 'success';
    default:
      return 'neutral';
  }
}

export function taskStatusVariant(status?: string): BadgeVariant {
  switch ((status ?? '').toUpperCase()) {
    case 'PENDING':
      return 'warning';
    case 'ASSIGNED':
      return 'info';
    case 'CLEANING':
      return 'cleaning';
    case 'INSPECTING':
      return 'inspecting';
    case 'INSPECTED':
      return 'success';
    default:
      return 'neutral';
  }
}
