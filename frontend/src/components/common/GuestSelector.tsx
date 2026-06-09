import React, { useState, useRef, useEffect } from 'react';

interface GuestSelectorProps {
  adults: number;
  children: number;
  onAdultsChange: (count: number) => void;
  onChildrenChange: (count: number) => void;
}

const ADULTS_MIN = 1;
const ADULTS_MAX = 8;
const CHILDREN_MIN = 0;
const CHILDREN_MAX = 6;

const GuestSelector: React.FC<GuestSelectorProps> = ({
  adults,
  children,
  onAdultsChange,
  onChildrenChange,
}) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const totalGuests = adults + children;
  const summary = `${adults} Adult${adults !== 1 ? 's' : ''}${
    children > 0 ? `, ${children} Child${children !== 1 ? 'ren' : ''}` : ''
  }`;

  const CounterButton: React.FC<{
    onClick: () => void;
    disabled: boolean;
    label: string;
    children: React.ReactNode;
  }> = ({ onClick, disabled, label, children: btnChildren }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="flex h-8 w-8 items-center justify-center rounded-full border border-neutral-300 text-neutral-600 transition-colors hover:border-primary-600 hover:text-primary-600 disabled:cursor-not-allowed disabled:border-neutral-200 disabled:text-neutral-300"
    >
      {btnChildren}
    </button>
  );

  return (
    <div className="relative" ref={ref}>
      <label className="mb-1 block text-xs font-medium text-neutral-600">
        Guests
      </label>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 transition-colors focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600"
      >
        <span>{totalGuests} Guest{totalGuests !== 1 ? 's' : ''}</span>
        <svg className={`h-3.5 w-3.5 text-neutral-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-64 rounded-lg border border-neutral-200 bg-white p-4 shadow-lg">
          <p className="mb-3 text-xs text-neutral-500">{summary}</p>

          {/* Adults */}
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral-800">Adults</p>
              <p className="text-xs text-neutral-400">Ages 13+</p>
            </div>
            <div className="flex items-center gap-3">
              <CounterButton
                onClick={() => onAdultsChange(adults - 1)}
                disabled={adults <= ADULTS_MIN}
                label="Decrease adults"
              >
                <span className="text-lg leading-none">&minus;</span>
              </CounterButton>
              <span className="w-6 text-center text-sm font-semibold text-neutral-800">
                {adults}
              </span>
              <CounterButton
                onClick={() => onAdultsChange(adults + 1)}
                disabled={adults >= ADULTS_MAX}
                label="Increase adults"
              >
                <span className="text-lg leading-none">+</span>
              </CounterButton>
            </div>
          </div>

          {/* Children */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral-800">Children</p>
              <p className="text-xs text-neutral-400">Ages 0-12</p>
            </div>
            <div className="flex items-center gap-3">
              <CounterButton
                onClick={() => onChildrenChange(children - 1)}
                disabled={children <= CHILDREN_MIN}
                label="Decrease children"
              >
                <span className="text-lg leading-none">&minus;</span>
              </CounterButton>
              <span className="w-6 text-center text-sm font-semibold text-neutral-800">
                {children}
              </span>
              <CounterButton
                onClick={() => onChildrenChange(children + 1)}
                disabled={children >= CHILDREN_MAX}
                label="Increase children"
              >
                <span className="text-lg leading-none">+</span>
              </CounterButton>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setOpen(false)}
            className="mt-4 w-full rounded-lg bg-primary-600 py-1.5 text-xs font-medium text-white hover:bg-primary-700 transition-colors"
          >
            Done
          </button>
        </div>
      )}
    </div>
  );
};

export default GuestSelector;
