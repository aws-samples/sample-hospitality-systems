import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, CreditCard } from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { usePropertyScope } from '../context/usePropertyScope';
import { pmsApi } from '../services/api';
import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  Pagination,
  Select,
  SkeletonRows,
  TBody,
  THead,
  Td,
  Th,
  Tr,
  folioStatusVariant,
} from '../components/ui';

const PAGE_SIZE = 50;

export default function BillingPage() {
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const {
    properties,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    scopeParams,
    noAccessibleProperties,
    selectedPropertyName,
  } = usePropertyScope();

  // Reset to page 1 whenever filter or property scope changes.
  useEffect(() => {
    setPage(1);
  }, [statusFilter, selectedPropertyId]);

  const { data, isLoading } = useQuery({
    queryKey: ['folios', selectedPropertyId, statusFilter, page],
    queryFn: async () => {
      const params = {
        ...(scopeParams ?? {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        page: String(page),
        limit: String(PAGE_SIZE),
      };
      const res = await pmsApi.get('/billing/folios', { params });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  const folios = data?.folios || [];
  const total: number = data?.pagination?.total ?? 0;

  return (
    <div data-testid="billing-page">
      <PageHeader
        title="Billing & Folios"
        subtitle={selectedPropertyName || undefined}
        actions={
          <>
            <PropertySelector
              properties={properties}
              selectedPropertyId={selectedPropertyId}
              onChange={setSelectedPropertyId}
              isChainLevel={isChainLevel}
              testId="billing-property-select"
            />
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All Folios</option>
              <option value="OPEN">Open</option>
              <option value="PENDING_PAYMENT">Pending Payment</option>
              <option value="PAID">Paid</option>
              <option value="VOID">Void</option>
            </Select>
          </>
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user.
        </div>
      )}

      {isLoading ? (
        <Card padding="none">
          <SkeletonRows rows={6} cols={6} />
        </Card>
      ) : folios.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={<CreditCard className="h-6 w-6" />}
            title="No folios found"
            description="Try changing the filter or selecting a different property."
          />
        </Card>
      ) : (
        <Card padding="none">
        <DataTable>
          <THead>
            <Tr hover={false}>
              <Th>Guest</Th>
              <Th>Check-In</Th>
              <Th>Check-Out</Th>
              <Th align="right">Total</Th>
              <Th>Status</Th>
              <Th>Paid At</Th>
              <Th align="right"></Th>
            </Tr>
          </THead>
          <TBody>
            {folios.map((folio: any) => (
              <Tr key={folio.folioId}>
                <Td className="text-neutral-900 font-medium">{folio.guestName}</Td>
                <Td>{folio.checkInDate}</Td>
                <Td>{folio.checkOutDate}</Td>
                <Td mono align="right" className="text-neutral-900 font-medium">
                  {folio.totalAmount != null ? `$${folio.totalAmount.toFixed(2)}` : '—'}
                </Td>
                <Td>
                  <Badge variant={folioStatusVariant(folio.status)}>{folio.status}</Badge>
                </Td>
                <Td className="text-xs text-neutral-500">
                  {folio.paidAt ? new Date(folio.paidAt).toLocaleString() : '—'}
                </Td>
                <Td align="right">
                  <Link
                    to={`/billing/${folio.folioId}`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-primary-600 hover:text-primary-700 transition-colors"
                  >
                    View
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Link>
                </Td>
              </Tr>
            ))}
          </TBody>
        </DataTable>
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={total}
          onPageChange={setPage}
          itemLabel="folios"
        />
        </Card>
      )}
    </div>
  );
}
