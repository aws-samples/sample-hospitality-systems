import React, { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import * as propertyService from '../services/propertyService';
import { useCart, type CreateCartParams } from '../context/CartContext';
import PropertyHero from '../components/property/PropertyHero';
import RoomTypeCard, { type RoomTypeData } from '../components/property/RoomTypeCard';
import ImageGallery from '../components/property/ImageGallery';
import DateRangePicker from '../components/common/DateRangePicker';
import GuestSelector from '../components/common/GuestSelector';
import LoadingSpinner from '../components/common/LoadingSpinner';
import PublicLayout from '../components/layout/PublicLayout';

const AMENITY_ICONS: Record<string, string> = {
  Pool: 'M2 18c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1 2.5-1 4-1',
  Spa: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z',
  Gym: 'M6.75 6.75h.75v10.5h-.75m9.75-10.5h.75v10.5H16.5M3.75 6.75h.75v10.5h-.75m15.75-10.5h.75v10.5h-.75M5.25 12h13.5',
  Restaurant: 'M12 3v6m0 0a3 3 0 003-3V3m-3 6a3 3 0 01-3-3V3m3 18v-9m6-6v3a3 3 0 01-3 3h0m-6 0h0a3 3 0 01-3-3V3',
  WiFi: 'M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z',
  Parking: 'M8.25 18.75a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h6m-9 0H3.375a1.125 1.125 0 01-1.125-1.125V14.25m17.25 4.5a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m3 0h1.125c.621 0 1.129-.504 1.09-1.124a17.902 17.902 0 00-3.213-9.193 2.056 2.056 0 00-1.58-.86H14.25M16.5 18.75h-2.25m0-11.177v-.958c0-.568-.422-1.048-.987-1.106a48.554 48.554 0 00-10.026 0 1.106 1.106 0 00-.987 1.106v7.635m12-6.677v6.677m0 4.5v-4.5m0 0h-12',
  'Room Service': 'M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.625 10.5a.375.375 0 11-.75 0 .375.375 0 01.75 0zm7.5 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z',
  Bar: 'M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5',
};

const PropertyDetailPage: React.FC = () => {
  const { propertyId } = useParams<{ propertyId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { createCart } = useCart();

  const [checkIn, setCheckIn] = useState(searchParams.get('checkIn') || '');
  const [checkOut, setCheckOut] = useState(searchParams.get('checkOut') || '');
  const [adults, setAdults] = useState(Number(searchParams.get('adults')) || 2);
  const [children, setChildren] = useState(Number(searchParams.get('children')) || 0);
  const [selectingRoom, setSelectingRoom] = useState(false);

  const { data: property, isLoading: propertyLoading } = useQuery({
    queryKey: ['property', propertyId],
    queryFn: () => propertyService.getProperty(propertyId!),
    enabled: !!propertyId,
  });

  const { data: roomTypes, isLoading: roomsLoading } = useQuery({
    queryKey: ['roomTypes', propertyId],
    queryFn: () => propertyService.getRoomTypes(propertyId!),
    enabled: !!propertyId,
  });

  const handleSelectRoom = async (roomType: RoomTypeData) => {
    if (!propertyId || !checkIn || !checkOut) {
      // Scroll to date picker area
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    setSelectingRoom(true);
    try {
      const params: CreateCartParams = {
        propertyId,
        roomTypeId: roomType.roomTypeId,
        ratePlanId: (roomType as any).bestAvailableRate?.ratePlanId || '',
        checkIn,
        checkOut,
        adults,
        children,
      };
      const cart = await createCart(params);
      navigate(`/booking/${cart.cartId}`);
    } catch (err) {
      console.error('Failed to create cart:', err);
    } finally {
      setSelectingRoom(false);
    }
  };

  if (propertyLoading) {
    return (
      <PublicLayout>
        <div className="flex min-h-[60vh] items-center justify-center">
          <LoadingSpinner size="lg" message="Loading property..." />
        </div>
      </PublicLayout>
    );
  }

  if (!property) {
    return (
      <PublicLayout>
        <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
          <h2 className="font-display text-2xl font-bold text-neutral-800">Property Not Found</h2>
          <p className="mt-2 text-neutral-500">The property you are looking for does not exist.</p>
          <button
            onClick={() => navigate('/search')}
            className="mt-6 rounded-lg bg-primary-600 px-6 py-2 text-sm font-semibold text-white hover:bg-primary-700 transition-colors"
          >
            Back to Search
          </button>
        </div>
      </PublicLayout>
    );
  }

  return (
    <PublicLayout>
      {/* Hero */}
      <PropertyHero property={property} />

      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        {/* Description */}
        <section className="max-w-3xl">
          <h2 className="font-display text-2xl font-bold text-neutral-900">About This Property</h2>
          <p className="mt-3 text-neutral-600 leading-relaxed">{property.description}</p>
        </section>

        {/* Image gallery */}
        {property.images && property.images.length > 1 && (
          <section className="mt-10">
            <ImageGallery images={property.images} propertyName={property.name} />
          </section>
        )}

        {/* Amenities grid */}
        {property.amenities.length > 0 && (
          <section className="mt-10">
            <h2 className="font-display text-2xl font-bold text-neutral-900">Amenities</h2>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {property.amenities.map((amenity) => (
                <div
                  key={amenity}
                  className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-3"
                >
                  <svg
                    className="h-5 w-5 shrink-0 text-primary-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={1.5}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d={AMENITY_ICONS[amenity] || 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z'}
                    />
                  </svg>
                  <span className="text-sm font-medium text-neutral-700">{amenity}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Availability & Room Types */}
        <section className="mt-12">
          <h2 className="font-display text-2xl font-bold text-neutral-900">Available Rooms</h2>

          {/* Date and guest selection */}
          <div className="mt-4 rounded-xl border border-neutral-200 bg-white p-5">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3 md:items-end">
              <div className="md:col-span-2">
                <DateRangePicker
                  checkIn={checkIn}
                  checkOut={checkOut}
                  onCheckInChange={setCheckIn}
                  onCheckOutChange={setCheckOut}
                />
              </div>
              <div>
                <GuestSelector
                  adults={adults}
                  children={children}
                  onAdultsChange={setAdults}
                  onChildrenChange={setChildren}
                />
              </div>
            </div>
            {!checkIn || !checkOut ? (
              <p className="mt-3 text-sm text-neutral-500">
                Select your dates to see available rooms and pricing.
              </p>
            ) : null}
          </div>

          {/* Room type list */}
          <div className="mt-6 space-y-4">
            {roomsLoading ? (
              <div className="flex justify-center py-10">
                <LoadingSpinner message="Loading rooms..." />
              </div>
            ) : roomTypes && roomTypes.length > 0 ? (
              roomTypes.map((room) => (
                <RoomTypeCard
                  key={room.roomTypeId}
                  roomType={room}
                  onSelect={handleSelectRoom}
                  checkIn={checkIn}
                  checkOut={checkOut}
                />
              ))
            ) : (
              <div className="rounded-xl border border-neutral-200 bg-white py-12 text-center">
                <p className="text-neutral-500">No rooms available for the selected dates.</p>
              </div>
            )}
          </div>

          {/* Loading overlay when selecting room */}
          {selectingRoom && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-xs">
              <div className="rounded-xl bg-white p-8 shadow-xl">
                <LoadingSpinner message="Creating your booking..." />
              </div>
            </div>
          )}
        </section>
      </div>
    </PublicLayout>
  );
};

export default PropertyDetailPage;
