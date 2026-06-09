import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock the auth context and the API client the hook depends on.
const mockAuth = { propertyId: null as string | null, groups: [] as string[] };
vi.mock('./AuthContext', () => ({
  useAuth: () => mockAuth,
}));

const mockGet = vi.fn();
vi.mock('../services/api', () => ({
  pmsApi: { get: (...args: unknown[]) => mockGet(...args) },
}));

import { usePropertyScope, CHAIN_WIDE } from './usePropertyScope';

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const PROPS = [
  { propertyId: 'p1', name: 'Bay Hotel' },
  { propertyId: 'p2', name: 'City Inn' },
];

beforeEach(() => {
  mockAuth.propertyId = null;
  mockAuth.groups = [];
  mockGet.mockReset();
  mockGet.mockResolvedValue({ data: { data: { properties: PROPS } } });
});

describe('usePropertyScope claim resolution', () => {
  it('property-scoped user is pinned to their JWT claim property', async () => {
    mockAuth.propertyId = 'p2';
    mockAuth.groups = ['FrontDesk'];
    const { result } = renderHook(() => usePropertyScope(), { wrapper });

    await waitFor(() => expect(result.current.selectedPropertyId).toBe('p2'));
    expect(result.current.isChainLevel).toBe(false);
    expect(result.current.scopeParams).toEqual({ propertyId: 'p2' });
    expect(result.current.isChainWide).toBe(false);
  });

  it('chain-level user defaults to the chain-wide aggregate when allowed', async () => {
    mockAuth.groups = ['Admin'];
    const { result } = renderHook(() => usePropertyScope({ allowChainWide: true }), { wrapper });

    await waitFor(() => expect(result.current.selectedPropertyId).toBe(CHAIN_WIDE));
    expect(result.current.isChainLevel).toBe(true);
    expect(result.current.isChainWide).toBe(true);
    // chain-wide -> empty scope params (no propertyId filter sent to backend)
    expect(result.current.scopeParams).toEqual({});
    expect(result.current.selectedPropertyName).toBe('All properties');
  });

  it('chain-level user on a per-property page falls back to first property', async () => {
    mockAuth.groups = ['Manager'];
    const { result } = renderHook(() => usePropertyScope({ allowChainWide: false }), { wrapper });

    // allowChainWide false -> no aggregate -> first property alphabetically.
    await waitFor(() => expect(result.current.selectedPropertyId).toBe('p1'));
    expect(result.current.scopeParams).toEqual({ propertyId: 'p1' });
    expect(result.current.selectedPropertyName).toBe('Bay Hotel');
  });

  it('reports no accessible properties when the list is empty', async () => {
    mockAuth.groups = ['Admin'];
    mockGet.mockResolvedValue({ data: { data: { properties: [] } } });
    const { result } = renderHook(() => usePropertyScope({ allowChainWide: false }), { wrapper });

    await waitFor(() => expect(result.current.propertiesLoading).toBe(false));
    expect(result.current.noAccessibleProperties).toBe(true);
  });

  it('setSelectedPropertyId switches scope to a specific property', async () => {
    mockAuth.groups = ['Admin'];
    const { result } = renderHook(() => usePropertyScope(), { wrapper });
    await waitFor(() => expect(result.current.selectedPropertyId).toBe(CHAIN_WIDE));

    act(() => result.current.setSelectedPropertyId('p2'));
    await waitFor(() => expect(result.current.selectedPropertyId).toBe('p2'));
    expect(result.current.scopeParams).toEqual({ propertyId: 'p2' });
    expect(result.current.isChainWide).toBe(false);
  });

  it('isChainLevel is false for a non-chain group', async () => {
    mockAuth.groups = ['Housekeeping'];
    mockAuth.propertyId = 'p1';
    const { result } = renderHook(() => usePropertyScope(), { wrapper });
    await waitFor(() => expect(result.current.selectedPropertyId).toBe('p1'));
    expect(result.current.isChainLevel).toBe(false);
  });
});
