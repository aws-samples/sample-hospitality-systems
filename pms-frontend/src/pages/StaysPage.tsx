import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { LogIn, LogOut, BedDouble } from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { usePropertyScope } from '../context/usePropertyScope';
import { pmsApi } from '../services/api';
import {
  Badge,
  Button,
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
  reservationStatusVariant,
  tierVariant,
} from '../components/ui';

const PAGE_SIZE = 50;

export default function StaysPage() {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const {
    properties,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    scopeParams,
    noAccessibleProperties,
    selectedPropertyName,
  } = usePropertyScope();

  // Reset to page 1 whenever the filter or property scope changes.
  useEffect(() => {
    setPage(1);
  }, [statusFilter, selectedPropertyId]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['stays', selectedPropertyId, statusFilter, page],
    queryFn: async () => {
      const params = {
        ...(scopeParams ?? {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        page: String(page),
        limit: String(PAGE_SIZE),
      };
      const res = await pmsApi.get('/stays', { params });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  const checkIn = useMutation({
    mutationFn: async (reservationId: string) => {
      const res = await pmsApi.post(`/stays/${reservationId}/checkin`, {});
      return res.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['stays'] }),
  });

  const checkOut = useMutation({
    mutationFn: async (reservationId: string) => {
      const res = await pmsApi.post(`/stays/${reservationId}/checkout`, { expressCheckout: true });
      return res.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['stays'] }),
  });

  const stays = data?.stays || [];
  const total = data?.pagination?.total ?? 0;

  return (
    <div data-testid="stays-page">
      <PageHeader
        title="Stays"
        subtitle={selectedPropertyName || undefined}
        actions={
          <>
            <PropertySelector
              properties={properties}
              selectedPropertyId={selectedPropertyId}
              onChange={setSelectedPropertyId}
              isChainLevel={isChainLevel}
              testId="stays-property-select"
            />
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              data-testid="stays-status-filter"
            >
              <option value="">Active Stays</option>
              <option value="CONFIRMED">Confirmed (Arriving)</option>
              <option value="CHECKED_IN">Checked In</option>
              <option value="CHECKED_OUT">Checked Out</option>
            </Select>
          </>
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user.
        </div>
      )}

      {error && (
        <Card padding="md" className="mb-4 border-red-200 bg-red-50">
          <p className="text-sm text-red-700">Failed to load stays: {String(error)}</p>
        </Card>
      )}

      {isLoading ? (
        <Card padding="none">
          <SkeletonRows rows={6} cols={7} />
        </Card>
      ) : stays.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={<BedDouble className="h-6 w-6" />}
            title="No stays found"
            description="Try changing the filter or selecting a different property."
          />
        </Card>
      ) : (
        <Card padding="none">
          <DataTable>
            <THead>
              <Tr hover={false}>
                <Th>Guest</Th>
                <Th>Tier</Th>
                <Th>Room Type</Th>
                <Th>Room #</Th>
                <Th>Check-In</Th>
                <Th>Check-Out</Th>
                <Th>Status</Th>
                <Th align="right">Actions</Th>
              </Tr>
            </THead>
            <TBody>
              {stays.map((stay: any) => (
                <Tr key={stay.reservationId}>
                  <Td className="text-neutral-900 font-medium">{stay.guestName}</Td>
                  <Td>
                    <Badge variant={tierVariant(stay.loyaltyTier)}>{stay.loyaltyTier}</Badge>
                  </Td>
                  <Td>{stay.roomType}</Td>
                  <Td mono className="text-neutral-900 font-medium">{stay.roomNumber || '—'}</Td>
                  <Td>{stay.checkInDate}</Td>
                  <Td>{stay.checkOutDate}</Td>
                  <Td>
                    <Badge variant={reservationStatusVariant(stay.status)}>{stay.status}</Badge>
                  </Td>
                  <Td align="right">
                    {stay.status === 'CONFIRMED' && (
                      <Button
                        size="sm"
                        variant="accent"
                        leftIcon={<LogIn className="h-3.5 w-3.5" />}
                        onClick={() => checkIn.mutate(stay.reservationId)}
                        loading={checkIn.isPending && checkIn.variables === stay.reservationId}
                        data-testid={`checkin-button-${stay.reservationId}`}
                      >
                        Check In
                      </Button>
                    )}
                    {stay.status === 'CHECKED_IN' && (
                      <Button
                        size="sm"
                        variant="primary"
                        leftIcon={<LogOut className="h-3.5 w-3.5" />}
                        onClick={() => checkOut.mutate(stay.reservationId)}
                        loading={checkOut.isPending && checkOut.variables === stay.reservationId}
                        data-testid={`checkout-button-${stay.reservationId}`}
                      >
                        Check Out
                      </Button>
                    )}
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
            itemLabel="stays"
          />
        </Card>
      )}
    </div>
  );
}
