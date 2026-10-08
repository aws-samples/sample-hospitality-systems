import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as propertyService from '../services/propertyService';
import SearchBar, { type SearchParams } from '../components/common/SearchBar';
import PropertyCard from '../components/property/PropertyCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PublicLayout from '../components/layout/PublicLayout';

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  const { data: properties, isLoading } = useQuery({
    queryKey: ['featuredProperties'],
    queryFn: () => propertyService.getProperties({ limit: 6 }),
  });

  const handleSearch = (params: SearchParams) => {
    const searchParams = new URLSearchParams();
    if (params.destination) searchParams.set('city', params.destination);
    if (params.checkIn) searchParams.set('checkIn', params.checkIn);
    if (params.checkOut) searchParams.set('checkOut', params.checkOut);
    searchParams.set('adults', String(params.adults));
    if (params.children > 0) searchParams.set('children', String(params.children));
    navigate(`/search?${searchParams.toString()}`);
  };

  return (
    <PublicLayout transparentHeader>
      {/* Hero Section */}
      <section className="relative flex min-h-[600px] items-center justify-center bg-linear-to-br from-primary-900 via-primary-700 to-primary-600">
        {/* Decorative background pattern */}
        <div className="absolute inset-0 opacity-10">
          <div
            className="h-full w-full"
            style={{
              backgroundImage:
                'radial-gradient(circle at 25% 25%, rgba(255,255,255,0.15) 0%, transparent 50%), radial-gradient(circle at 75% 75%, rgba(201,169,110,0.2) 0%, transparent 50%)',
            }}
          />
        </div>

        <div className="relative z-10 mx-auto w-full max-w-4xl px-4 py-20 text-center sm:px-6">
          <h1 className="font-display text-4xl font-bold text-white md:text-5xl lg:text-6xl">
            Discover Your Perfect Stay
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-white/80">
            Luxury hotels and resorts at world-class destinations. Book directly for the best rates and exclusive perks.
          </p>

          <div className="mt-10">
            <SearchBar onSearch={handleSearch} />
          </div>
        </div>
      </section>

      {/* Featured Properties */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="font-display text-3xl font-bold text-neutral-900">Featured Properties</h2>
          <p className="mt-2 text-neutral-600">
            Handpicked destinations for an unforgettable experience
          </p>
        </div>

        {isLoading ? (
          <div className="mt-12 flex justify-center">
            <LoadingSpinner size="lg" message="Loading properties..." />
          </div>
        ) : properties && properties.length > 0 ? (
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {properties.map((property) => (
              <PropertyCard
                key={property.propertyId}
                property={{
                  propertyId: property.propertyId,
                  name: property.name,
                  city: property.address.city,
                  state: property.address.state,
                  starRating: property.starRating,
                  heroImageUrl: property.images?.[0] ?? null,
                  amenities: property.amenities,
                }}
              />
            ))}
          </div>
        ) : (
          <div className="mt-12 text-center">
            <p className="text-neutral-500">No featured properties available at this time.</p>
          </div>
        )}
      </section>

      {/* Promo Banner */}
      <section className="bg-accent-500/10">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-4 rounded-2xl bg-linear-to-r from-primary-600 to-primary-800 p-8 text-center md:flex-row md:text-left">
            <div>
              <h3 className="font-display text-2xl font-bold text-white">
                Save 10% on Your First Booking
              </h3>
              <p className="mt-1 text-white/80">
                Use code <span className="font-mono font-bold text-accent-300">ANYCOMPANY10</span> at checkout for 10% off your first stay.
              </p>
            </div>
            <button
              onClick={() => navigate('/search')}
              className="shrink-0 rounded-lg bg-accent-500 px-8 py-3 text-sm font-semibold text-white hover:bg-accent-600 transition-colors"
            >
              Book Now
            </button>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
};

export default HomePage;
