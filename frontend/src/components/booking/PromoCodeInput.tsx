import React, { useState } from 'react';

interface PromoCodeInputProps {
  onApply: (code: string) => void;
  isLoading?: boolean;
  discount?: number | null;
  error?: string | null;
}

const PromoCodeInput: React.FC<PromoCodeInputProps> = ({
  onApply,
  isLoading = false,
  discount,
  error,
}) => {
  const [code, setCode] = useState('');

  const handleApply = () => {
    const trimmed = code.trim();
    if (trimmed) {
      onApply(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleApply();
    }
  };

  const hasDiscount = discount != null && discount > 0;

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-neutral-700">Promo Code</label>

      <div className="flex gap-2">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          placeholder="Enter promo code"
          disabled={isLoading || hasDiscount}
          className="flex-1 rounded-lg border border-neutral-300 px-3 py-2 text-sm text-neutral-800 uppercase tracking-wider placeholder:normal-case placeholder:tracking-normal transition-colors focus:border-primary-600 focus:outline-none focus:ring-1 focus:ring-primary-600 disabled:bg-neutral-50 disabled:cursor-not-allowed"
        />
        <button
          type="button"
          onClick={handleApply}
          disabled={isLoading || !code.trim() || hasDiscount}
          className="rounded-lg border border-primary-600 px-5 py-2 text-sm font-medium text-primary-600 hover:bg-primary-50 focus:outline-none focus:ring-2 focus:ring-primary-600/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            'Apply'
          )}
        </button>
      </div>

      {/* Success message */}
      {hasDiscount && (
        <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-2">
          <svg className="h-4 w-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm text-green-700">
            Promo applied! You save ${discount.toFixed(2)}
          </span>
        </div>
      )}

      {/* Error message */}
      {error && !hasDiscount && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2">
          <svg className="h-4 w-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span className="text-sm text-red-600">{error}</span>
        </div>
      )}
    </div>
  );
};

export default PromoCodeInput;
