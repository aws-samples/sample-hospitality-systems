import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
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
  CalendarPlus,
  LogIn,
  LogOut,
  Percent,
  DollarSign,
  TrendingUp,
  Sparkles,
  BedDouble,
  Receipt,
  CreditCard,
  XCircle,
  Moon,
} from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { usePropertyScope, CHAIN_WIDE } from '../context/usePropertyScope';
import { pmsApi } from '../services/api';
import {
  Card,
  CardHeader,
  CardBody,
  DataTable,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Skeleton,
  TBody,
  THead,
  Td,
  Th,
  Tr,
} from '../components/ui';
import type { ReactNode } from 'react';

const RANGE_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
];

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
  totals: {
    revenue: number;
    roomNightsSold: number;
    reservationsCreated: number;
    reservationsCancelled: number;
    checkIns: number;
    checkOuts: number;
    averageOccupancyPercent: number;
    totalRooms: number;
    propertyCount: number;
  };
  dailyBreakdown: DailyRow[];
}

interface OccupancyProperty {
  propertyId: string;
  name: string;
  city: string;
  totalRooms: number;
  occupiedRooms: number;
  occupancyPercent: number;
  revenueToday?: number;
  checkInsToday?: number;
  checkOutsToday?: number;
}

const fmtCurrency = (n: number) =>
  `$${(n ?? 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const fmtCompactCurrency = (n: number) => {
  if (Math.abs(n) >= 1000) return `$${Math.round(n / 100) / 10}k`;
  return `$${Math.round(n)}`;
};

const shortDate = (iso: string) => iso.slice(5); // MM-DD

export default function ReportsPage() {
  const {
    properties,
    propertiesLoading,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    noAccessibleProperties,
    selectedPropertyName,
    isChainWide,
  } = usePropertyScope({ allowChainWide: true });

  const [range, setRange] = useState('30');
  const [reportDate, setReportDate] = useState(
    new Date().toISOString().split('T')[0],
  );

  const days = Number(range);
  const endDate = reportDate;
  const startDate = (() => {
    const d = new Date(`${endDate}T00:00:00`);
    d.setDate(d.getDate() - (days - 1));
    return d.toISOString().split('T')[0];
  })();

  const rangePropertyParam = isChainWide ? '_all' : selectedPropertyId ?? '_all';

  const { data: rangeData, isLoading: rangeLoading } = useQuery<RangeResponse>({
    queryKey: ['reporting', 'range', rangePropertyParam, startDate, endDate],
    queryFn: async () => {
      const res = await pmsApi.get('/reporting/range', {
        params: {
          propertyId: rangePropertyParam,
          startDate,
          endDate,
        },
      });
      return res.data?.data;
    },
    enabled: !!selectedPropertyId,
  });

  const dailyPropertyId =
    selectedPropertyId && selectedPropertyId !== CHAIN_WIDE
      ? selectedPropertyId
      : null;

  const { data: daily, isLoading: dailyLoading } = useQuery({
    queryKey: ['reporting', 'daily', dailyPropertyId, reportDate],
    queryFn: async () => {
      const res = await pmsApi.get(`/reporting/${dailyPropertyId}/daily`, {
        params: { date: reportDate },
      });
      return res.data?.data;
    },
    enabled: !!dailyPropertyId,
    retry: false,
  });

  const { data: occupancy, isLoading: occupancyLoading } = useQuery({
    queryKey: ['reporting', 'occupancy', reportDate],
    queryFn: async () => {
      const res = await pmsApi.get('/reporting/occupancy', {
        params: { startDate: reportDate, endDate: reportDate },
      });
      return res.data?.data;
    },
  });

  const totals = rangeData?.totals;
  const breakdown = rangeData?.dailyBreakdown ?? [];
  const chartData = breakdown.map((d) => ({
    ...d,
    label: shortDate(d.date),
  }));

  const portfolioRows: OccupancyProperty[] = occupancy?.properties ?? [];

  return (
    <div data-testid="reports-page">
      <PageHeader
        title="Reports"
        subtitle={selectedPropertyName || undefined}
        actions={
          <>
            <PropertySelector
              properties={properties}
              selectedPropertyId={selectedPropertyId}
              onChange={setSelectedPropertyId}
              isChainLevel={isChainLevel}
              allowChainWide={true}
              testId="reports-property-select"
            />
            <Select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              data-testid="reports-range-select"
              className="min-w-40"
            >
              {RANGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            <Input
              type="date"
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
            />
          </>
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user.
        </div>
      )}

      {/* Period KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {rangeLoading || !totals ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))
        ) : (
          <>
            <Kpi
              label="Total Revenue"
              value={fmtCurrency(totals.revenue)}
              hint={`${days}-day room revenue`}
              icon={<DollarSign className="h-4 w-4" />}
            />
            <Kpi
              label="Room Nights Sold"
              value={totals.roomNightsSold.toLocaleString()}
              hint={`Avg occupancy ${totals.averageOccupancyPercent}%`}
              icon={<Moon className="h-4 w-4" />}
            />
            <Kpi
              label="Reservations Created"
              value={totals.reservationsCreated.toLocaleString()}
              hint={`${totals.checkIns} check-ins · ${totals.checkOuts} check-outs`}
              icon={<CalendarPlus className="h-4 w-4" />}
            />
            <Kpi
              label="Cancellations"
              value={totals.reservationsCancelled.toLocaleString()}
              hint={
                totals.reservationsCreated > 0
                  ? `${Math.round(
                      (totals.reservationsCancelled /
                        totals.reservationsCreated) *
                        100,
                    )}% of created`
                  : undefined
              }
              icon={<XCircle className="h-4 w-4" />}
            />
          </>
        )}
      </div>

      {/* Trend charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ChartCard
          title="Daily Revenue"
          subtitle={`${startDate} → ${endDate}`}
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

        <ChartCard
          title="Occupancy %"
          subtitle="Daily occupancy across selection"
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
                formatter={(v) => [`${v}%`, 'Occupancy']}
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
          title="Room Nights Sold"
          subtitle="Daily room-nights sold"
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
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(v) => [v, 'Room Nights']}
                labelFormatter={(label, payload) =>
                  payload?.[0]?.payload?.date ?? label
                }
              />
              <Bar
                dataKey="roomNightsSold"
                fill="#f59e0b"
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <Card padding="none">
          <CardHeader
            title="Portfolio Summary (Today)"
            subtitle={
              occupancy?.summary
                ? `${occupancy.summary.totalProperties ?? 0} properties · ${
                    occupancy.summary.overallOccupancy ?? 0
                  }% overall`
                : undefined
            }
          />
          <CardBody padding="none">
            {occupancyLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-4 w-full" />
                ))}
              </div>
            ) : !portfolioRows.length ? (
              <EmptyState title="No properties in scope" />
            ) : (
              <div className="max-h-56 overflow-y-auto">
                <DataTable className="border-0 rounded-none shadow-none">
                  <THead>
                    <Tr hover={false}>
                      <Th>Property</Th>
                      <Th align="right">Revenue</Th>
                      <Th align="right">Check-ins</Th>
                      <Th align="right">Check-outs</Th>
                      <Th align="right">Occ %</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {portfolioRows.map((p) => (
                      <Tr key={p.propertyId}>
                        <Td className="text-neutral-900 font-medium">
                          {p.name}
                        </Td>
                        <Td mono align="right">
                          {fmtCurrency(p.revenueToday ?? 0)}
                        </Td>
                        <Td mono align="right">
                          {p.checkInsToday ?? 0}
                        </Td>
                        <Td mono align="right">
                          {p.checkOutsToday ?? 0}
                        </Td>
                        <Td
                          mono
                          align="right"
                          className="text-neutral-900 font-semibold"
                        >
                          {p.occupancyPercent}%
                        </Td>
                      </Tr>
                    ))}
                  </TBody>
                </DataTable>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Today's Operations — only meaningful when a single property is in scope */}
      {dailyPropertyId && (
        <Card padding="none" className="mb-6">
          <CardHeader title="Today's Operations" subtitle={reportDate} />
          <CardBody padding="md">
            {dailyLoading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 rounded-lg" />
                ))}
              </div>
            ) : daily ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Metric
                  label="Reservations Created"
                  value={daily.reservationsCreated}
                  icon={<CalendarPlus className="h-4 w-4" />}
                />
                <Metric
                  label="Check-Ins"
                  value={daily.checkIns}
                  icon={<LogIn className="h-4 w-4" />}
                />
                <Metric
                  label="Check-Outs"
                  value={daily.checkOuts}
                  icon={<LogOut className="h-4 w-4" />}
                />
                <Metric
                  label="Occupancy"
                  value={`${daily.occupancy?.percent ?? 0}%`}
                  icon={<Percent className="h-4 w-4" />}
                />
                <Metric
                  label="Room Revenue"
                  hint={`${daily.roomsSold ?? 0} room-${
                    (daily.roomsSold ?? 0) === 1 ? 'night' : 'nights'
                  } sold`}
                  value={fmtCurrency(daily.revenue ?? 0)}
                  icon={<DollarSign className="h-4 w-4" />}
                />
                <Metric
                  label="ADR"
                  hint="Avg daily rate per room sold"
                  value={fmtCurrency(daily.adr ?? 0)}
                  icon={<TrendingUp className="h-4 w-4" />}
                />
                <Metric
                  label="Tax Posted"
                  value={fmtCurrency(daily.taxPosted ?? 0)}
                  icon={<Receipt className="h-4 w-4" />}
                />
                <Metric
                  label="Payments Collected"
                  hint={`${daily.paymentsCount ?? 0} payment${
                    (daily.paymentsCount ?? 0) === 1 ? '' : 's'
                  }`}
                  value={fmtCurrency(daily.paymentsCollected ?? 0)}
                  icon={<CreditCard className="h-4 w-4" />}
                />
                <Metric
                  label="Tasks Completed"
                  value={daily.housekeepingTasksCompleted}
                  icon={<Sparkles className="h-4 w-4" />}
                />
                <Metric
                  label="Rooms Occupied (now)"
                  value={`${daily.occupancy?.occupied ?? 0} / ${
                    daily.occupancy?.totalRooms ?? 0
                  }`}
                  icon={<BedDouble className="h-4 w-4" />}
                />
              </div>
            ) : (
              <p className="text-sm text-neutral-500">No data for {reportDate}</p>
            )}
          </CardBody>
        </Card>
      )}

      {/* Occupancy Across Properties (full table — historical position kept) */}
      {!propertiesLoading && (
        <Card padding="none">
          <CardHeader
            title="Occupancy Across Properties"
            subtitle={
              occupancy?.summary
                ? `${occupancy.summary.totalProperties ?? 0} properties · ${
                    occupancy.summary.overallOccupancy ?? 0
                  }% overall`
                : undefined
            }
          />
          <CardBody padding="none">
            {occupancyLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-4 w-full" />
                ))}
              </div>
            ) : !portfolioRows.length ? (
              <EmptyState title="No properties in scope" />
            ) : (
              <div className="max-h-112 overflow-y-auto">
                <DataTable className="border-0 rounded-none shadow-none">
                  <THead>
                    <Tr hover={false}>
                      <Th>Property</Th>
                      <Th>City</Th>
                      <Th align="right">Rooms</Th>
                      <Th align="right">Occupied</Th>
                      <Th align="right">Occupancy %</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {portfolioRows.map((p) => (
                      <Tr key={p.propertyId}>
                        <Td className="text-neutral-900 font-medium">{p.name}</Td>
                        <Td>{p.city}</Td>
                        <Td mono align="right">
                          {p.totalRooms}
                        </Td>
                        <Td mono align="right">
                          {p.occupiedRooms}
                        </Td>
                        <Td
                          mono
                          align="right"
                          className="text-neutral-900 font-semibold"
                        >
                          {p.occupancyPercent}%
                        </Td>
                      </Tr>
                    ))}
                  </TBody>
                </DataTable>
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  hint,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4 shadow-xs">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {label}
        </p>
        {icon && <span className="text-neutral-400">{icon}</span>}
      </div>
      <p className="font-display text-2xl font-bold text-neutral-900 mt-1">
        {value}
      </p>
      {hint && <p className="text-xs text-neutral-500 mt-0.5">{hint}</p>}
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  loading,
  children,
}: {
  title: string;
  subtitle?: string;
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <Card padding="none">
      <CardHeader title={title} subtitle={subtitle} />
      <CardBody padding="md">
        {loading ? <Skeleton className="h-[220px] w-full" /> : children}
      </CardBody>
    </Card>
  );
}

function Metric({
  label,
  value,
  icon,
  hint,
}: {
  label: string;
  value: any;
  icon?: ReactNode;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-neutral-50/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          {label}
        </p>
        {icon && <span className="text-neutral-400">{icon}</span>}
      </div>
      <p className="font-display text-xl font-bold text-neutral-900 mt-1">
        {value}
      </p>
      {hint && <p className="text-[10.5px] text-neutral-500 mt-0.5">{hint}</p>}
    </div>
  );
}
