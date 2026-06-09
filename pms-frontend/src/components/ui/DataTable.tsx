import { HTMLAttributes, ReactNode, TableHTMLAttributes, ThHTMLAttributes, TdHTMLAttributes } from 'react';

type DataTableProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
};

export function DataTable({ children, className = '', ...rest }: DataTableProps) {
  return (
    <div
      className={`overflow-x-auto rounded-xl border border-neutral-200 bg-white shadow-sm ${className}`}
      {...rest}
    >
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}

export function THead({ children, className = '', ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={`bg-neutral-50 border-b border-neutral-200 ${className}`} {...rest}>
      {children}
    </thead>
  );
}

export function TBody({ children, className = '', ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={className} {...rest}>
      {children}
    </tbody>
  );
}

export function TFoot({ children, className = '', ...rest }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tfoot className={`border-t border-neutral-200 bg-neutral-50/60 ${className}`} {...rest}>
      {children}
    </tfoot>
  );
}

type TableProps = TableHTMLAttributes<HTMLTableElement>;

export function Table({ children, className = '', ...rest }: TableProps) {
  return (
    <table className={`w-full text-sm ${className}`} {...rest}>
      {children}
    </table>
  );
}

type TrProps = HTMLAttributes<HTMLTableRowElement> & { hover?: boolean };

export function Tr({ children, hover = true, className = '', ...rest }: TrProps) {
  return (
    <tr
      className={`border-b border-neutral-100 last:border-0 ${
        hover ? 'hover:bg-neutral-50/70 transition-colors' : ''
      } ${className}`}
      {...rest}
    >
      {children}
    </tr>
  );
}

type ThProps = ThHTMLAttributes<HTMLTableCellElement> & { align?: 'left' | 'right' | 'center' };

export function Th({ children, align = 'left', className = '', ...rest }: ThProps) {
  const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';
  return (
    <th
      className={`${alignClass} px-4 py-3 text-xs font-semibold uppercase tracking-wide text-neutral-500 ${className}`}
      {...rest}
    >
      {children}
    </th>
  );
}

type TdProps = TdHTMLAttributes<HTMLTableCellElement> & { align?: 'left' | 'right' | 'center'; mono?: boolean };

export function Td({ children, align = 'left', mono = false, className = '', ...rest }: TdProps) {
  const alignClass = align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';
  const monoClass = mono ? 'font-mono tabular-nums' : '';
  return (
    <td className={`${alignClass} px-4 py-3 text-neutral-700 ${monoClass} ${className}`} {...rest}>
      {children}
    </td>
  );
}
