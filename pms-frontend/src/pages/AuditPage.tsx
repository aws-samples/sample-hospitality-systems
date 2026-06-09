import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import {
  BedDouble,
  Building2,
  Percent,
  ShoppingBag,
  DollarSign,
  Receipt,
  TrendingUp,
  Moon,
  PlayCircle,
  CheckCircle2,
} from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { useAuth } from '../context/AuthContext';
import { usePropertyScope } from '../context/usePropertyScope';
import { pmsApi } from '../services/api';
import {
  Button,
  Card,
  CardHeader,
  CardBody,
  EmptyState,
  Input,
  PageHeader,
  Skeleton,
} from '../components/ui';

export default function AuditPage() {
  const { groups } = useAuth();
  const isAdmin = groups.includes('Admin');

  const {
    properties,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    noAccessibleProperties,
    selectedPropertyName,
  } = usePropertyScope({ allowChainWide: false });

  const [reportDate, setReportDate] = useState(new Date().toISOString().split('T')[0]);
  const queryClient = useQueryClient();

  const auditPropertyId =
    selectedPropertyId && selectedPropertyId !== '__chain__' ? selectedPropertyId : null;

  const { data, isLoading } = useQuery({
    queryKey: ['audit', auditPropertyId, reportDate],
    queryFn: async () => {
      const res = await pmsApi.get(`/audit/reports/${auditPropertyId}`, {
        params: { date: reportDate },
      });
      return res.data?.data;
    },
    enabled: !!auditPropertyId,
    retry: false,
  });

  const trigger = useMutation({
    mutationFn: async () => {
      const res = await pmsApi.post('/audit/runs', { date: reportDate });
      return res.data?.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['audit'] }),
  });

  return (
    <div data-testid="audit-page">
      <PageHeader
        title="Night Audit"
        subtitle={selectedPropertyName || undefined}
        actions={
          <>
            <PropertySelector
              properties={properties}
              selectedPropertyId={selectedPropertyId}
              onChange={setSelectedPropertyId}
              isChainLevel={isChainLevel}
              allowChainWide={false}
              testId="audit-property-select"
            />
            <Input
              type="date"
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
            />
            {isAdmin && (
              <Button
                variant="accent"
                leftIcon={<PlayCircle className="h-4 w-4" />}
                onClick={() => trigger.mutate()}
                loading={trigger.isPending}
              >
                {trigger.isPending ? 'Running...' : 'Trigger Audit'}
              </Button>
            )}
          </>
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user.
        </div>
      )}

      {trigger.isSuccess && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg p-4 mb-6 text-sm flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
          Audit run triggered: {trigger.data?.propertiesProcessed} properties processed
        </div>
      )}

      {isLoading ? (
        <Card padding="md">
          <Skeleton className="h-6 w-48 mb-4" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Array.from({ length: 7 }).map((_, i) => (
              <Skeleton key={i} className="h-20 rounded-lg" />
            ))}
          </div>
        </Card>
      ) : auditPropertyId && !data ? (
        <Card padding="none">
          <EmptyState
            icon={<Moon className="h-6 w-6" />}
            title={`No audit report for ${reportDate}`}
            description={
              isAdmin ? 'Click "Trigger Audit" to generate one.' : 'Ask an admin to trigger an audit.'
            }
          />
        </Card>
      ) : data ? (
        <Card padding="none">
          <CardHeader
            title={`Audit Report — ${data.auditDate}`}
            subtitle={`Triggered by ${data.triggeredBy}`}
          />
          <CardBody padding="md">
            {data.metrics && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Metric
                  label="Total Rooms"
                  value={data.metrics.totalRooms}
                  icon={<Building2 className="h-4 w-4" />}
                />
                <Metric
                  label="Occupied"
                  value={data.metrics.occupiedRooms}
                  icon={<BedDouble className="h-4 w-4" />}
                />
                <Metric
                  label="Occupancy %"
                  value={`${data.metrics.occupancyPercent}%`}
                  icon={<Percent className="h-4 w-4" />}
                />
                <Metric
                  label="Rooms Sold"
                  value={data.metrics.roomsSold}
                  icon={<ShoppingBag className="h-4 w-4" />}
                />
                <Metric
                  label="Daily Revenue"
                  value={`$${(data.metrics.dailyRevenue ?? 0).toFixed(2)}`}
                  icon={<DollarSign className="h-4 w-4" />}
                />
                <Metric
                  label="Charges Posted"
                  value={data.metrics.chargesPosted}
                  icon={<Receipt className="h-4 w-4" />}
                />
                <Metric
                  label="ADR"
                  value={`$${(data.metrics.adr ?? 0).toFixed(2)}`}
                  icon={<TrendingUp className="h-4 w-4" />}
                />
              </div>
            )}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: any; icon?: ReactNode }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-neutral-50/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
        {icon && <span className="text-neutral-400">{icon}</span>}
      </div>
      <p className="font-display text-xl font-bold text-neutral-900 mt-1">{value}</p>
    </div>
  );
}
