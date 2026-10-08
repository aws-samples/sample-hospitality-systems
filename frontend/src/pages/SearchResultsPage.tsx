import React, { useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as bookingService from '../services/bookingService';
import PropertyCard from '../components/property/PropertyCard';
import SearchBar, { type SearchParams } from '../components/common/SearchBar';
import Pagination from '../components/common/Pagination';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PublicLayout from '../components/layout/PublicLayout';

const ITEMS_PER_PAGE = 12;

const AMENITY_OPTIONS = [
  'Pool',
  'Spa',
  'Gym',
  'Restaurant',
  'Bar',
  'Room Service',
  'WiFi',
  'Parking',
  'Pet Friendly',
  'Beach Access',
];

const SearchResultsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const city = searchParams.get('city') || '';
  const checkIn = searchParams.get('checkIn') || '';
  const checkOut = searchParams.get('checkOut') || '';
  const adults = Number(searchParams.get('adults')) || 2;
  const children = Number(searchParams.get('children')) || 0;

  // Filters
  const [priceRange, setPriceRange] = useState<[number, number]>([0, 1000]);
  const [starFilter, setStarFilter] = useState<number | null>(null);
  const [amenityFilters, setAmenityFilters] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const { data: results, isLoading } = useQuery({
    queryKey: ['searchProperties', city, checkIn, checkOut, adults, children],
    queryFn: () =>
      bookingService.searchProperties({
        destination: city,
        checkIn,
        checkOut,
        adults,
        children,
      }),
    enabled: true,
  });

  // Apply client-side filters
  const filteredResults = useMemo(() => {
    if (!results) return [];
    return results.filter((r) => {
      if (r.cheapestOption && (Number(r.cheapestOption.pricePerNight) < priceRange[0] || Number(r.cheapestOption.pricePerNight) > priceRange[1])) return false;
      if (starFilter && r.starRating < starFilter) return false;
      // Amenity filtering would require amenities on SearchResult; skip if not present
      return true;
    });
  }, [results, priceRange, starFilter, amenityFilters]);

  const totalPages = Math.ceil(filteredResults.length / ITEMS_PER_PAGE);
  const paginatedResults = filteredResults.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  const handleSearch = (params: SearchParams) => {
    const sp = new URLSearchParams();
    if (params.destination) sp.set('city', params.destination);
    if (params.checkIn) sp.set('checkIn', params.checkIn);
    if (params.checkOut) sp.set('checkOut', params.checkOut);
    sp.set('adults', String(params.adults));
    if (params.children > 0) sp.set('children', String(params.children));
    navigate(`/search?${sp.toString()}`);
    setCurrentPage(1);
  };

  const toggleAmenity = (amenity: string) => {
    setAmenityFilters((prev) =>
      prev.includes(amenity) ? prev.filter((a) => a !== amenity) : [...prev, amenity]
    );
    setCurrentPage(1);
  };

  return (
    <PublicLayout>
      {/* Search bar */}
      <div className="border-b border-neutral-200 bg-white py-4">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <SearchBar
            onSearch={handleSearch}
            initialValues={{ destination: city, checkIn, checkOut, adults, children }}
            compact
          />
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex gap-8">
          {/* Filters sidebar */}
          <aside className="hidden w-64 shrink-0 lg:block">
            <div className="sticky top-20 space-y-6">
              <h2 className="font-display text-lg font-semibold text-neutral-900">Filters</h2>

              {/* Price range */}
              <div>
                <h3 className="mb-2 text-sm font-medium text-neutral-700">Price Range</h3>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={priceRange[0]}
                    onChange={(e) => {
                      setPriceRange([Number(e.target.value), priceRange[1]]);
                      setCurrentPage(1);
                    }}
                    min={0}
                    className="w-24 rounded-lg border border-neutral-300 px-2 py-1.5 text-sm focus:border-primary-600 focus:outline-hidden focus:ring-1 focus:ring-primary-600"
                    placeholder="Min"
                  />
                  <span className="text-neutral-400">&mdash;</span>
                  <input
                    type="number"
                    value={priceRange[1]}
                    onChange={(e) => {
                      setPriceRange([priceRange[0], Number(e.target.value)]);
                      setCurrentPage(1);
                    }}
                    min={0}
                    className="w-24 rounded-lg border border-neutral-300 px-2 py-1.5 text-sm focus:border-primary-600 focus:outline-hidden focus:ring-1 focus:ring-primary-600"
                    placeholder="Max"
                  />
                </div>
              </div>

              {/* Star rating filter */}
              <div>
                <h3 className="mb-2 text-sm font-medium text-neutral-700">Star Rating</h3>
                <div className="flex gap-1.5">
                  {[3, 4, 5].map((star) => (
                    <button
                      key={star}
                      type="button"
                      onClick={() => {
                        setStarFilter(starFilter === star ? null : star);
                        setCurrentPage(1);
                      }}
                      className={`flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                        starFilter === star
                          ? 'border-primary-600 bg-primary-50 text-primary-700'
                          : 'border-neutral-300 text-neutral-600 hover:border-neutral-400'
                      }`}
                    >
                      {star}
                      <svg className="h-3.5 w-3.5 text-accent-500" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      +
                    </button>
                  ))}
                </div>
              </div>

              {/* Amenities */}
              <div>
                <h3 className="mb-2 text-sm font-medium text-neutral-700">Amenities</h3>
                <div className="space-y-2">
                  {AMENITY_OPTIONS.map((amenity) => (
                    <label key={amenity} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={amenityFilters.includes(amenity)}
                        onChange={() => toggleAmenity(amenity)}
                        className="h-4 w-4 rounded-sm border-neutral-300 text-primary-600 focus:ring-primary-600"
                      />
                      <span className="text-sm text-neutral-600">{amenity}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </aside>

          {/* Results */}
          <div className="flex-1">
            {/* Count */}
            <div className="mb-6 flex items-center justify-between">
              <h1 className="font-display text-2xl font-bold text-neutral-900">
                {city ? `Hotels in ${city}` : 'Search Results'}
              </h1>
              {!isLoading && (
                <p className="text-sm text-neutral-500">
                  {filteredResults.length} {filteredResults.length === 1 ? 'property' : 'properties'} found
                </p>
              )}
            </div>

            {isLoading ? (
              <div className="flex justify-center py-20">
                <LoadingSpinner size="lg" message="Searching properties..." />
              </div>
            ) : paginatedResults.length > 0 ? (
              <>
                <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
                  {paginatedResults.map((result) => (
                    <PropertyCard
                      key={result.propertyId}
                      property={{
                        propertyId: result.propertyId,
                        name: result.propertyName,
                        city: result.city,
                        state: result.state,
                        starRating: result.starRating,
                        heroImageUrl: result.heroImageUrl,
                        amenities: result.propertyAmenities || [],
                        cheapestRate: result.cheapestOption ? Number(result.cheapestOption.pricePerNight) : undefined,
                      }}
                      searchParams={{ checkIn, checkOut, adults, children }}
                    />
                  ))}
                </div>

                <div className="mt-10">
                  <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    onPageChange={setCurrentPage}
                  />
                </div>
              </>
            ) : (
              /* Empty state */
              <div className="rounded-xl border border-neutral-200 bg-white py-20 text-center">
                <svg
                  className="mx-auto h-16 w-16 text-neutral-300"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
                  />
                </svg>
                <h3 className="mt-4 font-display text-lg font-semibold text-neutral-700">
                  No properties found
                </h3>
                <p className="mt-1 text-sm text-neutral-500">
                  Try adjusting your search criteria or removing some filters.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </PublicLayout>
  );
};

export default SearchResultsPage;
