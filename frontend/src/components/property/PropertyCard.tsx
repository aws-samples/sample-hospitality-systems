import React from 'react';
import { useNavigate } from 'react-router-dom';
import ImagePlaceholder from '../common/ImagePlaceholder';
import StarRating from '../common/StarRating';

export interface PropertyCardData {
  propertyId: string;
  name: string;
  city: string;
  state?: string;
  country?: string;
  starRating: number;
  heroImageUrl?: string | null;
  amenities: string[];
  cheapestRate?: number;
  currency?: string;
}

interface PropertyCardProps {
  property: PropertyCardData;
  searchParams?: { checkIn?: string; checkOut?: string; adults?: number; children?: number };
}

const PropertyCard: React.FC<PropertyCardProps> = ({ property, searchParams }) => {
  const navigate = useNavigate();

  const location = [property.city, property.state].filter(Boolean).join(', ');
  const displayAmenities = property.amenities.slice(0, 4);

  const buildUrl = () => {
    const base = `/properties/${property.propertyId}`;
    if (!searchParams) return base;
    const sp = new URLSearchParams();
    if (searchParams.checkIn) sp.set('checkIn', searchParams.checkIn);
    if (searchParams.checkOut) sp.set('checkOut', searchParams.checkOut);
    if (searchParams.adults) sp.set('adults', String(searchParams.adults));
    if (searchParams.children) sp.set('children', String(searchParams.children));
    const qs = sp.toString();
    return qs ? `${base}?${qs}` : base;
  };

  return (
    <button
      type="button"
      onClick={() => navigate(buildUrl())}
      className="group w-full rounded-lg bg-white shadow-md hover:shadow-lg transition-shadow duration-300 overflow-hidden text-left focus:outline-none focus:ring-2 focus:ring-primary-600/40"
    >
      {/* Image */}
      <ImagePlaceholder
        src={property.heroImageUrl}
        alt={property.name}
        aspectRatio="4:3"
        icon="hotel"
        className="w-full"
      />

      {/* Content */}
      <div className="p-4">
        {/* Star rating */}
        <StarRating rating={property.starRating} size="sm" />

        {/* Name */}
        <h3 className="mt-1.5 font-display text-lg font-semibold text-neutral-900 group-hover:text-primary-600 transition-colors line-clamp-1">
          {property.name}
        </h3>

        {/* Location */}
        <p className="mt-0.5 text-sm text-neutral-500">{location}</p>

        {/* Amenity tags */}
        {displayAmenities.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {displayAmenities.map((amenity) => (
              <span
                key={amenity}
                className="inline-block rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700"
              >
                {amenity}
              </span>
            ))}
            {property.amenities.length > 4 && (
              <span className="inline-block rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-500">
                +{property.amenities.length - 4}
              </span>
            )}
          </div>
        )}

        {/* Price */}
        {property.cheapestRate != null && (
          <div className="mt-3 flex items-baseline gap-1 border-t border-neutral-100 pt-3">
            <span className="text-xs text-neutral-500">From</span>
            <span className="text-lg font-bold text-primary-600">
              ${property.cheapestRate.toFixed(0)}
            </span>
            <span className="text-xs text-neutral-400">/ night</span>
          </div>
        )}
      </div>
    </button>
  );
};

export default PropertyCard;
