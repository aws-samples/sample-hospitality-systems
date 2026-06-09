/**
 * Dropdown for chain-level users to pick a property (or aggregate).
 *
 * Renders nothing for property-scoped users — they only have access to one
 * property, so there's nothing to choose.
 */

import { CHAIN_WIDE, PropertyOption } from '../context/usePropertyScope';
import { Select } from './ui/Select';

interface Props {
  properties: PropertyOption[];
  selectedPropertyId: string | null;
  onChange: (id: string) => void;
  allowChainWide?: boolean;
  isChainLevel: boolean;
  testId?: string;
}

export default function PropertySelector({
  properties,
  selectedPropertyId,
  onChange,
  allowChainWide = true,
  isChainLevel,
  testId = 'property-select',
}: Props) {
  // Property-scoped users only ever have one property — hide the selector.
  if (!isChainLevel || properties.length <= 1) return null;

  return (
    <Select
      value={selectedPropertyId ?? ''}
      onChange={(e) => onChange(e.target.value)}
      data-testid={testId}
      className="min-w-[14rem]"
    >
      {allowChainWide && <option value={CHAIN_WIDE}>All properties (aggregate)</option>}
      {properties.map((p) => (
        <option key={p.propertyId} value={p.propertyId}>
          {p.name}
          {p.city ? ` — ${p.city}${p.state ? `, ${p.state}` : ''}` : ''}
        </option>
      ))}
    </Select>
  );
}
