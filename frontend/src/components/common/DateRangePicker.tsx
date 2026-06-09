import React, { useMemo } from 'react';
import { differenceInCalendarDays, parseISO } from 'date-fns';

interface DateRangePickerProps {
  checkIn: string;
  checkOut: string;
  onCheckInChange: (date: string) => void;
  onCheckOutChange: (date: string) => void;
  minDate?: string;
}

const DateRangePicker: React.FC<DateRangePickerProps> = ({
  checkIn,
  checkOut,
  onCheckInChange,
  onCheckOutChange,
  minDate,
}) => {
  const today = minDate ?? new Date().toISOString().split('T')[0];

  const nightCount = useMemo(() => {
    if (!checkIn || !checkOut) return 0;
    const diff = differenceInCalendarDays(parseISO(checkOut), parseISO(checkIn));
    return diff > 0 ? diff : 0;
  }, [checkIn, checkOut]);

  const handleCheckInChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newCheckIn = e.target.value;
    onCheckInChange(newCheckIn);

    // If check-out is before or equal to new check-in, clear it
    if (checkOut && checkOut <= newCheckIn) {
      onCheckOutChange('');
    }
  };

  const handleCheckOutChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newCheckOut = e.target.value;
    if (checkIn && newCheckOut <= checkIn) return;
    onCheckOutChange(newCheckOut);
  };

  const inputClass =
    'w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-800 ' +
    'focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 transition-colors';

  return (
    <div className="flex items-end gap-3">
      <div className="flex-1">
        <label className="mb-1 block text-xs font-medium text-neutral-600">
          Check-in
        </label>
        <input
          type="date"
          value={checkIn}
          min={today}
          onChange={handleCheckInChange}
          className={inputClass}
        />
      </div>

      {nightCount > 0 && (
        <div className="flex flex-col items-center pb-2">
          <span className="text-xs font-semibold text-primary-600">
            {nightCount}
          </span>
          <span className="text-[10px] text-neutral-400">
            {nightCount === 1 ? 'night' : 'nights'}
          </span>
        </div>
      )}

      <div className="flex-1">
        <label className="mb-1 block text-xs font-medium text-neutral-600">
          Check-out
        </label>
        <input
          type="date"
          value={checkOut}
          min={checkIn || today}
          onChange={handleCheckOutChange}
          className={inputClass}
        />
      </div>
    </div>
  );
};

export default DateRangePicker;
