import React, { useState } from 'react';
import DateRangePicker from './DateRangePicker';
import GuestSelector from './GuestSelector';

export interface SearchParams {
  destination: string;
  checkIn: string;
  checkOut: string;
  adults: number;
  children: number;
}

interface SearchBarProps {
  onSearch: (params: SearchParams) => void;
  initialValues?: Partial<SearchParams>;
  compact?: boolean;
}

const defaultValues: SearchParams = {
  destination: '',
  checkIn: '',
  checkOut: '',
  adults: 2,
  children: 0,
};

const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  initialValues,
  compact = false,
}) => {
  const [params, setParams] = useState<SearchParams>({
    ...defaultValues,
    ...initialValues,
  });

  const update = (field: keyof SearchParams, value: string | number) => {
    setParams((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(params);
  };

  if (compact) {
    return (
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-4 py-1.5 shadow-xs"
      >
        <input
          type="text"
          value={params.destination}
          onChange={(e) => update('destination', e.target.value)}
          placeholder="Where to?"
          className="w-32 border-none bg-transparent text-sm text-neutral-800 placeholder-neutral-400 focus:outline-hidden"
        />
        <span className="text-neutral-300">|</span>
        <input
          type="date"
          value={params.checkIn}
          onChange={(e) => update('checkIn', e.target.value)}
          className="w-[120px] border-none bg-transparent text-sm text-neutral-800 focus:outline-hidden"
        />
        <span className="text-neutral-300">|</span>
        <input
          type="date"
          value={params.checkOut}
          onChange={(e) => update('checkOut', e.target.value)}
          min={params.checkIn}
          className="w-[120px] border-none bg-transparent text-sm text-neutral-800 focus:outline-hidden"
        />
        <button
          type="submit"
          className="ml-1 flex h-8 w-8 items-center justify-center rounded-full bg-primary-600 text-white transition-colors hover:bg-primary-700"
          aria-label="Search"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607z" />
          </svg>
        </button>
      </form>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full rounded-2xl bg-white p-4 shadow-lg md:p-6"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-12 md:items-end">
        {/* Destination */}
        <div className="md:col-span-3">
          <label className="mb-1 block text-xs font-medium text-neutral-600">
            Destination
          </label>
          <div className="relative">
            <svg
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0z" />
            </svg>
            <input
              type="text"
              value={params.destination}
              onChange={(e) => update('destination', e.target.value)}
              placeholder="City, hotel, or destination"
              className="w-full rounded-lg border border-neutral-300 bg-white py-2 pl-9 pr-3 text-sm text-neutral-800 placeholder-neutral-400 transition-colors focus:border-primary-600 focus:outline-hidden focus:ring-1 focus:ring-primary-600"
            />
          </div>
        </div>

        {/* Dates */}
        <div className="md:col-span-5">
          <DateRangePicker
            checkIn={params.checkIn}
            checkOut={params.checkOut}
            onCheckInChange={(d) => update('checkIn', d)}
            onCheckOutChange={(d) => update('checkOut', d)}
          />
        </div>

        {/* Guests */}
        <div className="md:col-span-2">
          <GuestSelector
            adults={params.adults}
            children={params.children}
            onAdultsChange={(n) => update('adults', n)}
            onChildrenChange={(n) => update('children', n)}
          />
        </div>

        {/* Search button */}
        <div className="md:col-span-2">
          <button
            type="submit"
            className="w-full rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700 focus:outline-hidden focus:ring-2 focus:ring-primary-600/40"
          >
            Search
          </button>
        </div>
      </div>
    </form>
  );
};

export default SearchBar;
