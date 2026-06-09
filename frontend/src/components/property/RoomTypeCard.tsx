import React from 'react';
import { differenceInCalendarDays, parseISO } from 'date-fns';
import ImagePlaceholder from '../common/ImagePlaceholder';

export interface RoomTypeData {
  roomTypeId: string;
  name: string;
  description: string;
  maxOccupancy: number;
  bedConfiguration: string;
  squareFootage: number;
  amenities: string[];
  images: string[];
  baseRate: number;
}

interface RoomTypeCardProps {
  roomType: RoomTypeData;
  onSelect: (roomType: RoomTypeData) => void;
  checkIn?: string;
  checkOut?: string;
}

const RoomTypeCard: React.FC<RoomTypeCardProps> = ({
  roomType,
  onSelect,
  checkIn,
  checkOut,
}) => {
  const heroImage = roomType.images?.[0] ?? null;

  const nights =
    checkIn && checkOut
      ? differenceInCalendarDays(parseISO(checkOut), parseISO(checkIn))
      : 0;

  const rate = Number(roomType.baseRate) || 0;
  const totalPrice = nights > 0 ? rate * nights : null;
  const displayAmenities = roomType.amenities.slice(0, 6);

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm md:flex-row">
      {/* Image */}
      <div className="w-full md:w-72 lg:w-80 shrink-0">
        <ImagePlaceholder
          src={heroImage}
          alt={roomType.name}
          aspectRatio="3:2"
          icon="room"
          className="h-full w-full"
        />
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col p-5">
        <div className="flex-1">
          <h3 className="font-display text-xl font-semibold text-neutral-900">
            {roomType.name}
          </h3>
          <p className="mt-1.5 text-sm text-neutral-600 line-clamp-2">
            {roomType.description}
          </p>

          {/* Room details */}
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-neutral-500">
            <span className="flex items-center gap-1">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0" />
              </svg>
              Up to {roomType.maxOccupancy} guests
            </span>
            <span className="flex items-center gap-1">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75" />
              </svg>
              {roomType.squareFootage} sq ft
            </span>
            <span className="flex items-center gap-1">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-2.25 1.313m-13.5 0L3 16.5v-2.25" />
              </svg>
              {roomType.bedConfiguration}
            </span>
          </div>

          {/* Amenity tags */}
          {displayAmenities.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {displayAmenities.map((amenity) => (
                <span
                  key={amenity}
                  className="inline-block rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-600"
                >
                  {amenity}
                </span>
              ))}
              {roomType.amenities.length > 6 && (
                <span className="inline-block rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-400">
                  +{roomType.amenities.length - 6} more
                </span>
              )}
            </div>
          )}
        </div>

        {/* Price and action */}
        <div className="mt-4 flex items-end justify-between border-t border-neutral-100 pt-4">
          <div>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-bold text-primary-600">
                ${rate.toFixed(0)}
              </span>
              <span className="text-sm text-neutral-400">/ night</span>
            </div>
            {totalPrice != null && (
              <p className="mt-0.5 text-sm text-neutral-500">
                ${totalPrice.toFixed(0)} total for {nights} {nights === 1 ? 'night' : 'nights'}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={() => onSelect(roomType)}
            className="rounded-lg bg-accent-500 px-6 py-2.5 text-sm font-semibold text-white hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-400 focus:ring-offset-2 transition-colors"
          >
            Select Room
          </button>
        </div>
      </div>
    </div>
  );
};

export default RoomTypeCard;
