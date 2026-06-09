import { useQuery } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { Building2, LogIn, KeyRound, Sparkles } from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { usePropertyScope } from '../context/usePropertyScope';
import { pmsApi } from '../services/api';
import {
  Badge,
  Card,
  PageHeader,
  Skeleton,
  SkeletonCards,
  roomStatusVariant,
} from '../components/ui';

type AccentKey = 'primary' | 'success' | 'emerald' | 'accent';

const ACCENT_BORDER: Record<AccentKey, string> = {
  primary: 'border-l-primary-600',
  success: 'border-l-emerald-500',
  emerald: 'border-l-emerald-500',
  accent: 'border-l-accent-500',
};

const ACCENT_ICON_BG: Record<AccentKey, string> = {
  primary: 'bg-primary-50 text-primary-600',
  success: 'bg-emerald-50 text-emerald-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  accent: 'bg-accent-50 text-accent-700',
};

export default function DashboardPage() {
  const {
    properties,
    propertiesLoading,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    scopeParams,
    noAccessibleProperties,
    selectedPropertyName,
    isChainWide,
  } = usePropertyScope();

  const { data: stays, isLoading: staysLoading } = useQuery({
    queryKey: ['stays', selectedPropertyId, 'checked_in'],
    queryFn: async () => {
      const params = { status: 'CHECKED_IN', ...(scopeParams ?? {}) };
      const res = await pmsApi.get('/stays', { params });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['housekeeping', 'summary', selectedPropertyId],
    queryFn: async () => {
      const res = await pmsApi.get('/housekeeping/rooms/summary', { params: scopeParams });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  const isLoading = propertiesLoading || staysLoading || summaryLoading;

  return (
    <div data-testid="dashboard-page">
      <PageHeader
        title="Property Dashboard"
        subtitle={selectedPropertyName || undefined}
        actions={
          <PropertySelector
            properties={properties}
            selectedPropertyId={selectedPropertyId}
            onChange={setSelectedPropertyId}
            isChainLevel={isChainLevel}
            testId="dashboard-property-select"
          />
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user. Ask an admin to assign a property
          (property-scoped users) or grant a chain-level role.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-6">
          <SkeletonCards count={4} />
          <Card padding="md">
            <Skeleton className="h-5 w-40 mb-4" />
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16 rounded-lg" />
              ))}
            </div>
          </Card>
        </div>
      ) : (
        <>
          {/* Key Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <MetricCard
              label="Occupancy"
              value={`${summary?.occupancyPercent ?? 0}%`}
              icon={<Building2 className="h-5 w-5" strokeWidth={1.75} />}
              accent="primary"
              testId="metric-occupancy"
            />
            <MetricCard
              label="Checked In"
              value={stays?.pagination?.total ?? 0}
              icon={<LogIn className="h-5 w-5" strokeWidth={1.75} />}
              accent="success"
              testId="metric-arrivals"
            />
            <MetricCard
              label="Rooms Available"
              value={summary?.available ?? 0}
              icon={<KeyRound className="h-5 w-5" strokeWidth={1.75} />}
              accent="emerald"
              testId="metric-available"
            />
            <MetricCard
              label="Rooms Dirty"
              value={(summary?.dirty ?? 0) + (summary?.cleaning ?? 0)}
              icon={<Sparkles className="h-5 w-5" strokeWidth={1.75} />}
              accent="accent"
              testId="metric-dirty"
            />
          </div>

          {/* Room Status Summary */}
          <Card padding="md" className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-lg font-semibold text-neutral-900">Room Status</h2>
              <span className="text-sm text-neutral-500">
                {isChainWide ? 'Chain-wide total' : 'Total'}: {summary?.totalRooms ?? 0}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatusTile label="Available" count={summary?.available ?? 0} status="AVAILABLE" />
              <StatusTile label="Occupied" count={summary?.occupied ?? 0} status="OCCUPIED" />
              <StatusTile label="Dirty" count={summary?.dirty ?? 0} status="DIRTY" />
              <StatusTile label="Cleaning" count={summary?.cleaning ?? 0} status="CLEANING" />
              <StatusTile label="Inspecting" count={summary?.inspecting ?? 0} status="INSPECTING" />
              <StatusTile label="Out of Order" count={summary?.outOfOrder ?? 0} status="OUT_OF_ORDER" />
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  icon,
  accent,
  testId,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  accent: AccentKey;
  testId: string;
}) {
  return (
    <Card
      padding="md"
      className={`border-l-4 ${ACCENT_BORDER[accent]}`}
      data-testid={testId}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
          <p className="font-display text-3xl font-bold text-neutral-900 mt-1.5">{value}</p>
        </div>
        <div
          className={`flex-shrink-0 inline-flex h-10 w-10 items-center justify-center rounded-full ${ACCENT_ICON_BG[accent]}`}
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}

function StatusTile({ label, count, status }: { label: string; count: number; status: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-3 text-center">
      <p className="font-display text-2xl font-bold text-neutral-900">{count}</p>
      <div className="mt-1.5">
        <Badge variant={roomStatusVariant(status)}>{label}</Badge>
      </div>
    </div>
  );
}
