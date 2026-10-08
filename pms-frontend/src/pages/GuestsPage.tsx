import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Search, Users } from 'lucide-react';
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
  THead,
  Td,
  Th,
  Tr,
  tierVariant,
} from '../components/ui';

interface GuestRow {
  guestId: string;
  guestName: string;
  email: string;
  phone: string | null;
  loyaltyTier: string;
  pointsBalance: number;
  totalStays: number;
  lastStayDate: string | null;
  nextStayDate: string | null;
}

const TIERS = ['ALL', 'DIAMOND', 'GOLD', 'SILVER', 'NONE'] as const;

export default function GuestsPage() {
  const [selectedGuestId, setSelectedGuestId] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [tier, setTier] = useState<(typeof TIERS)[number]>('ALL');

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(searchInput.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  const PAGE_SIZE = 100;

  const {
    data: guestsData,
    isLoading: guestsLoading,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useInfiniteQuery<{
    guests: GuestRow[];
    pagination: { page: number; limit: number; total: number; totalPages: number };
  }>({
    queryKey: ['guests', debouncedQ, tier],
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => {
      const params: Record<string, string> = {
        limit: String(PAGE_SIZE),
        page: String(pageParam),
        sort: 'recent',
      };
      if (debouncedQ) params.q = debouncedQ;
      if (tier !== 'ALL') params.tier = tier;
      const res = await pmsApi.get('/guests', { params });
      return res.data?.data;
    },
    getNextPageParam: (lastPage) => {
      const { page, totalPages } = lastPage.pagination;
      return page < totalPages ? page + 1 : undefined;
    },
  });

  const guests: GuestRow[] = guestsData?.pages.flatMap((p) => p.guests) || [];
  const totalGuests: number = guestsData?.pages[0]?.pagination?.total ?? guests.length;

  // IntersectionObserver sentinel: fetch the next page when the trigger
  // scrolls into the directory's viewport.
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      { root: node.parentElement, rootMargin: '100px' },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, guests.length]);

  const { data: loyalty, isLoading: loyaltyLoading } = useQuery({
    queryKey: ['loyalty', selectedGuestId],
    queryFn: async () => {
      const res = await pmsApi.get(`/loyalty/${selectedGuestId}`);
      return res.data?.data;
    },
    enabled: !!selectedGuestId,
  });

  const { data: transactions, isLoading: txLoading } = useQuery({
    queryKey: ['loyalty-transactions', selectedGuestId],
    queryFn: async () => {
      const res = await pmsApi.get(`/loyalty/${selectedGuestId}/transactions`, {
        params: { limit: 10 },
      });
      return res.data?.data;
    },
    enabled: !!selectedGuestId,
  });

  return (
    <div data-testid="guests-page">
      <PageHeader title="Guests" subtitle={`${totalGuests.toLocaleString()} total`} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card padding="none" className="lg:col-span-1">
          <CardHeader
            title="Directory"
            subtitle={`Showing ${guests.length.toLocaleString()} of ${totalGuests.toLocaleString()}`}
          />
          <div className="px-4 py-3 border-b border-neutral-100 space-y-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 pointer-events-none" />
              <input
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search name or email"
                className="w-full pl-9 pr-3 py-2 text-sm rounded-md border border-neutral-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-hidden"
              />
            </div>
            <div className="flex flex-wrap gap-1">
              {TIERS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTier(t)}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                    tier === t
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'bg-white text-neutral-600 border-neutral-200 hover:bg-neutral-50'
                  }`}
                >
                  {t === 'ALL' ? 'All' : t}
                </button>
              ))}
            </div>
          </div>

          <div className="max-h-112 overflow-y-auto">
            {guestsLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : guests.length === 0 ? (
              <EmptyState
                icon={<Users className="h-6 w-6" />}
                title="No guests"
                description={debouncedQ || tier !== 'ALL' ? 'Try a different search or tier.' : 'No guests in the system.'}
              />
            ) : (
              <>
                {guests.map((g) => {
                  const isSelected = selectedGuestId === g.guestId;
                  return (
                    <button
                      key={g.guestId}
                      onClick={() => setSelectedGuestId(g.guestId)}
                      className={`w-full text-left px-4 py-3 border-b border-neutral-100 last:border-0 transition-colors ${
                        isSelected
                          ? 'bg-primary-50 border-l-4 border-l-primary-600 pl-3'
                          : 'hover:bg-neutral-50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-medium text-neutral-900 truncate">{g.guestName}</p>
                        <Badge variant={tierVariant(g.loyaltyTier)}>{g.loyaltyTier}</Badge>
                      </div>
                      <p className="text-xs text-neutral-500 truncate mt-0.5">{g.email}</p>
                      {g.nextStayDate && (
                        <p className="text-xs text-emerald-700 mt-0.5">Next stay: {g.nextStayDate}</p>
                      )}
                    </button>
                  );
                })}
                {hasNextPage && (
                  <div ref={sentinelRef} className="px-4 py-3 text-center text-xs text-neutral-500">
                    {isFetchingNextPage ? 'Loading more…' : ''}
                  </div>
                )}
              </>
            )}
          </div>
        </Card>

        <div className="lg:col-span-2 space-y-4">
          {!selectedGuestId ? (
            <Card padding="none">
              <EmptyState
                icon={<Users className="h-6 w-6" />}
                title="Select a guest"
                description="Choose a guest from the list to view loyalty details and recent transactions."
              />
            </Card>
          ) : (
            <>
              <Card padding="md">
                {loyaltyLoading || !loyalty ? (
                  <div className="space-y-4">
                    <Skeleton className="h-6 w-48" />
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-16 rounded-lg" />
                      ))}
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center justify-between gap-4 mb-4">
                      <h2 className="font-display text-xl font-semibold text-neutral-900">
                        {loyalty.guestName}
                      </h2>
                      <Badge variant={tierVariant(loyalty.tier)}>{loyalty.tier}</Badge>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <Metric label="Tier" value={loyalty.tier} />
                      <Metric
                        label="Points"
                        value={loyalty.pointsBalance?.toLocaleString() ?? '0'}
                      />
                      <Metric
                        label="Lifetime"
                        value={loyalty.lifetimePointsEarned?.toLocaleString() ?? '0'}
                      />
                      <Metric label="Total Stays" value={loyalty.totalStays ?? 0} />
                    </div>
                    {loyalty.nextTier && (
                      <p className="mt-4 text-sm text-neutral-600">
                        <span className="font-medium">{loyalty.staysToNextTier}</span> more stays to
                        reach{' '}
                        <Badge variant={tierVariant(loyalty.nextTier)}>{loyalty.nextTier}</Badge>
                      </p>
                    )}
                  </>
                )}
              </Card>

              <Card padding="none">
                <CardHeader title="Recent Transactions" />
                <CardBody padding="none">
                  {txLoading || !transactions ? (
                    <div className="p-4 space-y-3">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-4 w-full" />
                      ))}
                    </div>
                  ) : transactions.transactions.length === 0 ? (
                    <EmptyState title="No transactions yet" />
                  ) : (
                    <div className="overflow-x-auto">
                      <Table>
                        <THead>
                          <Tr hover={false}>
                            <Th>Date</Th>
                            <Th>Type</Th>
                            <Th align="right">Points</Th>
                            <Th align="right">Balance</Th>
                          </Tr>
                        </THead>
                        <TBody>
                          {transactions.transactions.map((t: any) => (
                            <Tr key={t.transactionId}>
                              <Td className="text-xs text-neutral-500">
                                {new Date(t.createdAt).toLocaleDateString()}
                              </Td>
                              <Td>{t.type}</Td>
                              <Td
                                mono
                                align="right"
                                className={t.points > 0 ? 'text-emerald-700 font-medium' : 'text-red-700 font-medium'}
                              >
                                {t.points > 0 ? '+' : ''}
                                {t.points}
                              </Td>
                              <Td mono align="right" className="text-neutral-700">
                                {t.balanceAfter?.toLocaleString()}
                              </Td>
                            </Tr>
                          ))}
                        </TBody>
                      </Table>
                    </div>
                  )}
                </CardBody>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: any }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-neutral-50/60 p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="font-display text-xl font-bold text-neutral-900 mt-1">{value}</p>
    </div>
  );
}
