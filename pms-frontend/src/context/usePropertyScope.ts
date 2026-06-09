/**
 * Shared hook to resolve the property scope for the signed-in PMS user.
 *
 * Rules:
 *   - Property-scoped users (FrontDesk, Housekeeping): pinned to their
 *     assigned property. If the `custom:property_id` claim is missing from
 *     the ID token, falls back to the first property the backend says they
 *     can access.
 *   - Chain-level users (Admin, Manager, RevenueManager): may choose any
 *     property from the dropdown, or an "All properties" aggregate where the
 *     caller does not pass a propertyId.
 *   - Regional users (RegionalManager): backend narrows to their region; UX
 *     is the same as chain-level (pick a property or leave unscoped).
 *
 * Every PMS page that needs a property context should use this hook so the
 * behavior is consistent across Dashboard, Reports, Night Audit, etc.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { pmsApi } from '../services/api';
import { useAuth } from './AuthContext';

export const CHAIN_WIDE = '__chain__';

const CHAIN_LEVEL_GROUPS = new Set([
  'Admin',
  'Manager',
  'RevenueManager',
  'RegionalManager',
]);

export interface PropertyOption {
  propertyId: string;
  name: string;
  city?: string;
  state?: string;
  region?: string;
}

export interface PropertyScope {
  properties: PropertyOption[];
  propertiesLoading: boolean;
  isChainLevel: boolean;
  selectedPropertyId: string | null;
  setSelectedPropertyId: (id: string) => void;
  /** Query-string params to forward to backend calls (empty object = chain aggregate). */
  scopeParams: Record<string, string> | null;
  /** `true` when the backend returned zero accessible properties. */
  noAccessibleProperties: boolean;
  /** Display name for the current selection. */
  selectedPropertyName: string;
  /** When `true`, the current selection represents the chain-wide aggregate. */
  isChainWide: boolean;
}

export function usePropertyScope(options: {
  /** If `true`, expose the "All properties (aggregate)" option for chain-level users. */
  allowChainWide?: boolean;
} = {}): PropertyScope {
  const { allowChainWide = true } = options;
  const { propertyId: claimPropertyId, groups } = useAuth();

  const isChainLevel = useMemo(
    () => groups.some((g) => CHAIN_LEVEL_GROUPS.has(g)),
    [groups],
  );

  const { data, isLoading: propertiesLoading } = useQuery({
    queryKey: ['pms-properties'],
    queryFn: async () => {
      const res = await pmsApi.get('/properties');
      return res.data?.data as { properties: PropertyOption[] };
    },
  });

  const properties: PropertyOption[] = data?.properties ?? [];
  const noAccessibleProperties = !propertiesLoading && properties.length === 0;

  const [selectedPropertyId, setSelectedPropertyId] = useState<string | null>(null);

  useEffect(() => {
    if (selectedPropertyId) return;
    // 1. Honor the explicit JWT claim when present (property-scoped users).
    if (claimPropertyId) {
      setSelectedPropertyId(claimPropertyId);
      return;
    }
    // 2. Chain-level user on a page that supports the chain-wide aggregate?
    //    Default to the aggregate so they see all properties at once.
    if (isChainLevel && allowChainWide) {
      setSelectedPropertyId(CHAIN_WIDE);
      return;
    }
    // 3. Otherwise pick the first accessible property. For property-scoped
    //    users without a claim this is their single property; for chain-level
    //    users on per-property pages (Reports, Night Audit) it's the first
    //    one alphabetically — and the selector lets them switch.
    if (properties.length > 0) {
      setSelectedPropertyId(properties[0].propertyId);
    }
  }, [claimPropertyId, isChainLevel, allowChainWide, properties, selectedPropertyId]);

  const scopeParams: Record<string, string> | null = useMemo(() => {
    if (!selectedPropertyId) return null;
    if (selectedPropertyId === CHAIN_WIDE) return {} as Record<string, string>;
    return { propertyId: selectedPropertyId };
  }, [selectedPropertyId]);

  const selectedPropertyName = useMemo(() => {
    if (!selectedPropertyId) return '';
    if (selectedPropertyId === CHAIN_WIDE) return 'All properties';
    const match = properties.find((p) => p.propertyId === selectedPropertyId);
    return match?.name ?? '';
  }, [selectedPropertyId, properties]);

  return {
    properties,
    propertiesLoading,
    isChainLevel,
    selectedPropertyId,
    setSelectedPropertyId,
    scopeParams,
    noAccessibleProperties,
    selectedPropertyName,
    isChainWide: selectedPropertyId === CHAIN_WIDE,
  };
}
