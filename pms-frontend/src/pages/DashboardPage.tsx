import { useQuery } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import {
  Building2,
  LogIn,
  LogOut,
  KeyRound,
  Sparkles,
  CalendarPlus,
  DollarSign,
  BedDouble,
  CreditCard,
  Users,
  BarChart3,
} from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { usePropertyScope } from '../context/usePropertyScope';
import { useAuth } from '../context/AuthContext';
import { pmsApi } from '../services/api';
import {
  Badge,
  Card,
  CardHeader,
  CardBody,
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

interface DailyRow {
  date: string;
  revenue: number;
  roomNightsSold: number;
  occupancyPercent: number;
  reservationsCreated: number;
  reservationsCancelled: number;
  checkIns: number;
  checkOuts: number;
}

interface RangeResponse {
  propertyId: string;
  startDate: string;
  endDate: string;
  totals: Record<string, number>;
  dailyBreakdown: DailyRow[];
}

const TREND_DAYS = 14;

const fmtCurrency = (n: number) =>
  `$${(n ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;

const fmtCompactCurrency = (n: number) => {
  if (Math.abs(n) >= 1000) return `$${Math.round(n / 100) / 10}k`;
  return `$${Math.round(n)}`;};

const shortDate = (iso: string) => iso.slice(5); // MM-DD

function todayStr() {
  return new Date().toISOString().split('T')[0];
}

function daysAgoStr(end: string, n: number) {
  const d = new Date(`${end}T00:00:00`);
  d.setDate(d.getDate() - n);
  return d.toISOString().split('T')[0];
}

// Quick-action links mirror the sidebar's role gating so a user only sees
// destinations they can actually reach.
const QUICK_ACTIONS: {
  to: string;
  label: string;
  icon: ReactNode;
  roles: string[];
}[] = [
  { to: '/stays', label: 'Stays', icon: <BedDouble className="h-4 w-4" />, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { to: '/housekeeping', label: 'Housekeeping', icon: <Sparkles className="h-4 w-4" />, roles: ['Admin', 'Manager', 'Housekeeping'] },
  { to: '/billing', label: 'Billing', icon: <CreditCard className="h-4 w-4" />, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { to: '/guests', label: 'Guests', icon: <Users className="h-4 w-4" />, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { to: '/reports', label: 'Reports', icon: <BarChart3 className="h-4 w-4" />, roles: ['Admin', 'Manager', 'RegionalManager', 'RevenueManager'] },
];

export default function DashboardPage() {
  const { groups } = useAuth();
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

  // Reporting-derived activity + trends. The /reporting/* endpoints are
  // restricted to manager-and-above groups, which is exactly `isChainLevel`,
  // so we only fetch (and render) these sections for those roles. Front-desk
  // and housekeeping keep the live room-state view below.
  const end = todayStr();
  const start = daysAgoStr(end, TREND_DAYS - 1);
  const rangePropertyParam = isChainWide ? '_all' : selectedPropertyId ?? '_all';

  const { data: range, isLoading: rangeLoading } = useQuery<RangeResponse>({
    queryKey: ['reporting', 'range', rangePropertyParam, start, end],
    queryFn: async () => {
      const res = await pmsApi.get('/reporting/range', {
        params: { propertyId: rangePropertyParam, startDate: start, endDate: end },
      });
      return res.data?.data;
    },
    enabled: isChainLevel && !!selectedPropertyId,
  });

  const breakdown = range?.dailyBreakdown ?? [];
  const chartData = breakdown.map((d) => ({ ...d, label: shortDate(d.date) }));
  // "Today" KPIs come from the final row of the range (date === end).
  const todayRow = breakdown.length ? breakdown[breakdown.length - 1] : undefined;

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
          {/* Live room-state metrics — available to every staff role. */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <MetricCard
              label="Occupancy (In-House)"
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

          {/* Today's activity + trends — manager-and-above only (reporting API). */}
          {isChainLevel && (
            <>
              <div
                className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
                data-testid="dashboard-activity"
              >
                {rangeLoading ? (
                  Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-24 rounded-lg" />
                  ))
                ) : (
                  <>
                    <ActivityCard
                      label="Check-ins Today"
                      value={todayRow?.checkIns ?? 0}
                      icon={<LogIn className="h-4 w-4" />}
                    />
                    <ActivityCard
                      label="Check-outs Today"
                      value={todayRow?.checkOuts ?? 0}
                      icon={<LogOut className="h-4 w-4" />}
                    />
                    <ActivityCard
                      label="New Reservations"
                      value={todayRow?.reservationsCreated ?? 0}
                      icon={<CalendarPlus className="h-4 w-4" />}
                    />
                    <ActivityCard
                      label="Today's Revenue"
                      value={fmtCurrency(todayRow?.revenue ?? 0)}
                      icon={<DollarSign className="h-4 w-4" />}
                    />
                  </>
                )}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                <ChartCard
                  title={`Booked Occupancy % (Last ${TREND_DAYS} days)`}
                  loading={rangeLoading}
                >
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={chartData} margin={{ left: 0, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 10 }}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fontSize: 10 }}
                        tickFormatter={(v) => `${v}%`}
                      />
                      <Tooltip
                        formatter={(v) => [`${v}%`, 'Booked occupancy']}
                        labelFormatter={(label, payload) =>
                          payload?.[0]?.payload?.date ?? label
                        }
                      />
                      <Line
                        type="monotone"
                        dataKey="occupancyPercent"
                        stroke="#10b981"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </ChartCard>

                <ChartCard
                  title={`Revenue (Last ${TREND_DAYS} days)`}
                  loading={rangeLoading}
                >
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 10 }}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 10 }}
                        tickFormatter={(v) => fmtCompactCurrency(v as number)}
                      />
                      <Tooltip
                        formatter={(v) => [fmtCurrency(v as number), 'Revenue']}
                        labelFormatter={(label, payload) =>
                          payload?.[0]?.payload?.date ?? label
                        }
                      />
                      <Bar dataKey="revenue" fill="#6366f1" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </div>
            </>
          )}

          {/* Room Status — available to every staff role. */}
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

          {/* Quick Actions — links role-filtered to reachable destinations. */}
          <QuickActions groups={groups} />
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

function ActivityCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
}) {
  return (
    <Card padding="md">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
        <span className="text-neutral-400">{icon}</span>
      </div>
      <p className="font-display text-2xl font-bold text-neutral-900 mt-1">{value}</p>
    </Card>
  );
}

function ChartCard({
  title,
  loading,
  children,
}: {
  title: string;
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <Card padding="none">
      <CardHeader title={title} />
      <CardBody padding="md">
        {loading ? <Skeleton className="h-[220px] w-full" /> : children}
      </CardBody>
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

function QuickActions({ groups }: { groups: string[] }) {
  const actions = QUICK_ACTIONS.filter((a) => a.roles.some((r) => groups.includes(r)));
  if (!actions.length) return null;
  return (
    <Card padding="md" data-testid="dashboard-quick-actions">
      <h2 className="font-display text-lg font-semibold text-neutral-900 mb-3">Quick Actions</h2>
      <div className="flex flex-wrap gap-3">
        {actions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className="inline-flex items-center gap-2 rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-semibold text-neutral-800 hover:bg-neutral-50 transition-colors"
          >
            <span className="text-primary-600">{a.icon}</span>
            {a.label}
          </Link>
        ))}
      </div>
    </Card>
  );
}
