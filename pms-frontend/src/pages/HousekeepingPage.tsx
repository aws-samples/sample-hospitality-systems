import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Sparkles, Check, CheckCircle2, XCircle, UserPlus } from 'lucide-react';
import PropertySelector from '../components/PropertySelector';
import { useAuth } from '../context/AuthContext';
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
  priorityVariant,
  roomStatusVariant,
  taskStatusVariant,
} from '../components/ui';

interface Task {
  taskId: string;
  roomNumber: string;
  taskType: string;
  priority: string;
  status: string;
  assignedTo?: string | null;
}

// The completion / inspection actions kick off a Step Functions workflow that
// runs 2–3 Lambdas asynchronously. The HTTP response returns before those
// finish, so a naive refetch sees the intermediate task.status. We optimistic-
// update the cache to the expected post-SFN value and poll briefly so the UI
// converges without a manual refresh.
const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 5;
const PAGE_SIZE = 50;

export default function HousekeepingPage() {
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const {
    properties,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    scopeParams,
    noAccessibleProperties,
    selectedPropertyName,
    isChainWide,
  } = usePropertyScope();

  // Reset to page 1 whenever filter or property scope changes.
  useEffect(() => {
    setPage(1);
  }, [statusFilter, selectedPropertyId]);

  const tasksQueryKey = ['housekeeping', 'tasks', selectedPropertyId, statusFilter, page];

  const { data: tasksData, isLoading } = useQuery({
    queryKey: tasksQueryKey,
    queryFn: async () => {
      const params = {
        ...(scopeParams ?? {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        page: String(page),
        limit: String(PAGE_SIZE),
      };
      const res = await pmsApi.get('/housekeeping/tasks', { params });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  const { data: roomsData } = useQuery({
    queryKey: ['housekeeping', 'rooms', selectedPropertyId],
    queryFn: async () => {
      const res = await pmsApi.get('/housekeeping/rooms/summary', { params: scopeParams });
      return res.data?.data;
    },
    enabled: !!scopeParams,
  });

  // Patch a single task's status in every cached `housekeeping/tasks` query so
  // the UI reflects the expected post-SFN state immediately.
  function patchCachedTaskStatus(taskId: string, nextStatus: string, extras: Partial<Task> = {}) {
    queryClient.setQueriesData<{ tasks?: Task[] } | undefined>(
      { queryKey: ['housekeeping', 'tasks'] },
      (current) => {
        if (!current?.tasks) return current;
        return {
          ...current,
          tasks: current.tasks.map((t) =>
            t.taskId === taskId ? { ...t, status: nextStatus, ...extras } : t,
          ),
        };
      },
    );
  }

  // Poll until the server-reported status for `taskId` matches `expectedStatus`,
  // or we hit POLL_MAX_ATTEMPTS. Cancels itself when the property scope changes.
  const pollTimerRef = useRef<number | null>(null);
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    };
  }, []);

  function pollUntilTaskStatus(taskId: string, expectedStatus: string | string[]) {
    const targets = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus];
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      // Refetch both tasks and rooms summary so the dashboard counters update too.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['housekeeping', 'tasks'] }),
        queryClient.invalidateQueries({ queryKey: ['housekeeping', 'rooms'] }),
        queryClient.invalidateQueries({ queryKey: ['housekeeping', 'summary'] }),
      ]);

      // Read the freshest cached task and decide whether to keep polling.
      const fresh = queryClient.getQueriesData<{ tasks?: Task[] } | undefined>({
        queryKey: ['housekeeping', 'tasks'],
      });
      const found = fresh
        .map(([, data]) => data?.tasks?.find((t) => t.taskId === taskId))
        .find(Boolean);

      const converged = found ? targets.includes(found.status) : false;
      if (converged || attempts >= POLL_MAX_ATTEMPTS) return;

      pollTimerRef.current = window.setTimeout(tick, POLL_INTERVAL_MS);
    };
    pollTimerRef.current = window.setTimeout(tick, POLL_INTERVAL_MS);
  }

  const assign = useMutation({
    mutationFn: async ({ taskId, assignedTo }: { taskId: string; assignedTo: string }) => {
      const res = await pmsApi.put(`/housekeeping/tasks/${taskId}/assign`, { assignedTo });
      return res.data;
    },
    onMutate: ({ taskId, assignedTo }) => {
      // Assign is fully synchronous on the backend (no SFN), so the optimistic
      // update is just for snappy UI; invalidate handles the rest.
      patchCachedTaskStatus(taskId, 'ASSIGNED', { assignedTo });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['housekeeping'] });
    },
  });

  const complete = useMutation({
    mutationFn: async (taskId: string) => {
      const res = await pmsApi.post(`/housekeeping/tasks/${taskId}/complete`, { notes: 'Cleaned' });
      return res.data;
    },
    onMutate: (taskId) => {
      // Backend writes COMPLETED, but the SFN immediately advances to
      // INSPECTING. Show INSPECTING right away (Pass/Fail buttons), then poll.
      patchCachedTaskStatus(taskId, 'INSPECTING');
    },
    onSuccess: (_data, taskId) => {
      pollUntilTaskStatus(taskId, 'INSPECTING');
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['housekeeping'] });
    },
  });

  const inspect = useMutation({
    mutationFn: async ({ taskId, passed }: { taskId: string; passed: boolean }) => {
      const res = await pmsApi.post(`/housekeeping/tasks/${taskId}/inspect`, { passed });
      return res.data;
    },
    onMutate: ({ taskId, passed }) => {
      // Pass → SFN ends with task INSPECTED, room AVAILABLE.
      // Fail → SFN loops back; task lands in CLEANING with a fresh token.
      patchCachedTaskStatus(taskId, passed ? 'INSPECTED' : 'CLEANING');
    },
    onSuccess: (_data, { taskId, passed }) => {
      pollUntilTaskStatus(taskId, passed ? 'INSPECTED' : ['CLEANING', 'ASSIGNED']);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['housekeeping'] });
    },
  });

  const tasks: Task[] = tasksData?.tasks || [];
  const tasksTotal: number = tasksData?.pagination?.total ?? 0;

  return (
    <div data-testid="housekeeping-page">
      <PageHeader
        title="Housekeeping"
        subtitle={selectedPropertyName || undefined}
        actions={
          <PropertySelector
            properties={properties}
            selectedPropertyId={selectedPropertyId}
            onChange={setSelectedPropertyId}
            isChainLevel={isChainLevel}
            testId="housekeeping-property-select"
          />
        }
      />

      {noAccessibleProperties && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4 mb-6 text-sm">
          No accessible properties found for this user.
        </div>
      )}

      {/* Room Status Summary */}
      {roomsData && (
        <Card padding="md" className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-semibold text-neutral-900">Room Status</h2>
            <span className="text-xs text-neutral-500">
              {isChainWide ? 'Chain-wide total' : 'Total'}: {roomsData.totalRooms ?? 0}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatusTile label="Available" count={roomsData.available || 0} status="AVAILABLE" />
            <StatusTile label="Occupied" count={roomsData.occupied || 0} status="OCCUPIED" />
            <StatusTile label="Dirty" count={roomsData.dirty || 0} status="DIRTY" />
            <StatusTile label="Cleaning" count={roomsData.cleaning || 0} status="CLEANING" />
            <StatusTile label="Inspecting" count={roomsData.inspecting || 0} status="INSPECTING" />
            <StatusTile label="Out of Order" count={roomsData.outOfOrder || 0} status="OUT_OF_ORDER" />
          </div>
        </Card>
      )}

      <div className="flex items-center justify-between mb-4 gap-3">
        <h2 className="font-display text-xl font-semibold text-neutral-900">Tasks</h2>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="PENDING">Pending</option>
          <option value="ASSIGNED">Assigned</option>
          <option value="CLEANING">Cleaning</option>
          <option value="INSPECTING">Inspecting</option>
          <option value="INSPECTED">Inspected</option>
        </Select>
      </div>

      {isLoading ? (
        <Card padding="none">
          <SkeletonRows rows={5} cols={6} />
        </Card>
      ) : tasks.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={<Sparkles className="h-6 w-6" />}
            title="No tasks found"
            description="Try changing the filter or selecting a different property."
          />
        </Card>
      ) : (
        <Card padding="none">
        <DataTable>
          <THead>
            <Tr hover={false}>
              <Th>Room</Th>
              <Th>Type</Th>
              <Th>Priority</Th>
              <Th>Status</Th>
              <Th>Assigned To</Th>
              <Th align="right">Actions</Th>
            </Tr>
          </THead>
          <TBody>
            {tasks.map((task) => {
              const isAssigning = assign.isPending && assign.variables?.taskId === task.taskId;
              const isCompleting = complete.isPending && complete.variables === task.taskId;
              const isInspecting = inspect.isPending && inspect.variables?.taskId === task.taskId;
              return (
                <Tr key={task.taskId}>
                  <Td mono className="text-neutral-900 font-medium">{task.roomNumber}</Td>
                  <Td>{task.taskType}</Td>
                  <Td>
                    <Badge variant={priorityVariant(task.priority)}>{task.priority}</Badge>
                  </Td>
                  <Td>
                    <Badge variant={taskStatusVariant(task.status)}>{task.status}</Badge>
                  </Td>
                  <Td>{task.assignedTo || '—'}</Td>
                  <Td align="right">
                    <div className="inline-flex items-center gap-2 justify-end">
                      {task.status === 'PENDING' && (
                        <Button
                          size="sm"
                          variant="primary"
                          leftIcon={<UserPlus className="h-3.5 w-3.5" />}
                          loading={isAssigning}
                          onClick={() => assign.mutate({ taskId: task.taskId, assignedTo: user?.email ?? 'staff' })}
                        >
                          Assign
                        </Button>
                      )}
                      {(task.status === 'ASSIGNED' || task.status === 'CLEANING') && (
                        <Button
                          size="sm"
                          variant="accent"
                          leftIcon={<Check className="h-3.5 w-3.5" />}
                          loading={isCompleting}
                          onClick={() => complete.mutate(task.taskId)}
                        >
                          Complete
                        </Button>
                      )}
                      {task.status === 'INSPECTING' && (
                        <>
                          <Button
                            size="sm"
                            variant="success"
                            leftIcon={<CheckCircle2 className="h-3.5 w-3.5" />}
                            loading={isInspecting && inspect.variables?.passed === true}
                            onClick={() => inspect.mutate({ taskId: task.taskId, passed: true })}
                          >
                            Pass
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            leftIcon={<XCircle className="h-3.5 w-3.5" />}
                            loading={isInspecting && inspect.variables?.passed === false}
                            onClick={() => inspect.mutate({ taskId: task.taskId, passed: false })}
                          >
                            Fail
                          </Button>
                        </>
                      )}
                    </div>
                  </Td>
                </Tr>
              );
            })}
          </TBody>
        </DataTable>
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={tasksTotal}
          onPageChange={setPage}
          itemLabel="tasks"
        />
        </Card>
      )}
    </div>
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
