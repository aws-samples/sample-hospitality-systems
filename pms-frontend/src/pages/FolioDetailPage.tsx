import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { pmsApi } from '../services/api';
import {
  Badge,
  Card,
  CardHeader,
  CardBody,
  EmptyState,
  PageHeader,
  Skeleton,
  Table,
  TBody,
  TFoot,
  THead,
  Td,
  Th,
  Tr,
  folioStatusVariant,
} from '../components/ui';

const fmtCurrency = (n?: number | null) =>
  n == null ? '—' : `$${Number(n).toFixed(2)}`;

export default function FolioDetailPage() {
  const { folioId } = useParams();

  const { data, isLoading } = useQuery({
    queryKey: ['folio', folioId],
    queryFn: async () => {
      const res = await pmsApi.get(`/billing/folios/${folioId}`);
      return res.data?.data;
    },
    enabled: !!folioId,
  });

  if (isLoading) {
    return (
      <div data-testid="folio-detail-page" className="space-y-6">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-10 w-64" />
        <Card padding="md">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <Skeleton className="h-3 w-16 mb-2" />
                <Skeleton className="h-5 w-24" />
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div data-testid="folio-detail-page">
        <Link
          to="/billing"
          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 mb-4"
        >
          <ChevronLeft className="h-4 w-4" />
          Back to Folios
        </Link>
        <Card padding="none">
          <EmptyState title="Folio not found" />
        </Card>
      </div>
    );
  }

  const folio = data.folio;
  const charges = data.charges || [];
  const payments = data.payments || [];

  return (
    <div data-testid="folio-detail-page">
      <Link
        to="/billing"
        className="inline-flex items-center gap-1 text-sm font-medium text-primary-600 hover:text-primary-700 mb-4 transition-colors"
      >
        <ChevronLeft className="h-4 w-4" />
        Back to Folios
      </Link>

      <PageHeader title="Folio Detail" subtitle={folio.guestName} />

      <Card padding="md" className="mb-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
          <SummaryField label="Guest" value={folio.guestName} />
          <SummaryField
            label="Dates"
            value={`${folio.checkInDate} → ${folio.checkOutDate}`}
          />
          <SummaryField
            label="Status"
            value={<Badge variant={folioStatusVariant(folio.status)}>{folio.status}</Badge>}
          />
          <SummaryField label="Total" value={fmtCurrency(folio.totalAmount)} mono />
        </div>
      </Card>

      <Card padding="none" className="mb-6">
        <CardHeader title="Charges" />
        <CardBody padding="none">
          {charges.length === 0 ? (
            <EmptyState title="No charges posted" />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <Tr hover={false}>
                    <Th>Date</Th>
                    <Th>Type</Th>
                    <Th>Description</Th>
                    <Th align="right">Amount</Th>
                    <Th>Status</Th>
                  </Tr>
                </THead>
                <TBody>
                  {charges.map((c: any) => (
                    <Tr key={c.chargeId}>
                      <Td>{c.chargeDate}</Td>
                      <Td>{c.chargeType}</Td>
                      <Td className="text-neutral-900">{c.description}</Td>
                      <Td mono align="right" className="text-neutral-900 font-medium">
                        {fmtCurrency(c.amount)}
                      </Td>
                      <Td className="text-xs text-neutral-500">{c.status}</Td>
                    </Tr>
                  ))}
                </TBody>
                <TFoot>
                  <tr>
                    <td colSpan={3} className="px-4 py-2 text-right text-sm font-medium text-neutral-600">
                      Subtotal
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-sm font-medium text-neutral-800">
                      {fmtCurrency(folio.subtotal ?? 0)}
                    </td>
                    <td />
                  </tr>
                  <tr>
                    <td colSpan={3} className="px-4 py-2 text-right text-sm font-medium text-neutral-600">
                      Tax
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-sm font-medium text-neutral-800">
                      {fmtCurrency(folio.taxAmount ?? 0)}
                    </td>
                    <td />
                  </tr>
                  <tr className="border-t-2 border-neutral-300">
                    <td colSpan={3} className="px-4 py-3 text-right font-display text-base font-bold text-neutral-900">
                      Total
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-base font-bold text-neutral-900">
                      {fmtCurrency(folio.totalAmount ?? 0)}
                    </td>
                    <td />
                  </tr>
                </TFoot>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>

      <Card padding="none">
        <CardHeader title="Payments" />
        <CardBody padding="none">
          {payments.length === 0 ? (
            <EmptyState title="No payments recorded" />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <THead>
                  <Tr hover={false}>
                    <Th>Date</Th>
                    <Th>Method</Th>
                    <Th align="right">Amount</Th>
                    <Th>Status</Th>
                  </Tr>
                </THead>
                <TBody>
                  {payments.map((p: any) => (
                    <Tr key={p.paymentId}>
                      <Td>{new Date(p.createdAt).toLocaleString()}</Td>
                      <Td>{p.method}</Td>
                      <Td mono align="right" className="text-neutral-900 font-medium">
                        {fmtCurrency(p.amount)}
                      </Td>
                      <Td className="text-xs text-neutral-500">{p.status}</Td>
                    </Tr>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function SummaryField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
      <p
        className={`mt-1 text-base font-medium text-neutral-900 ${
          mono ? 'font-mono tabular-nums' : ''
        }`}
      >
        {value}
      </p>
    </div>
  );
}
