import React from 'react';
import ImagePlaceholder from '../common/ImagePlaceholder';
import StarRating from '../common/StarRating';

interface PropertyHeroProps {
  property: {
    name: string;
    address: {
      city: string;
      state?: string;
      country: string;
    };
    starRating: number;
    images?: string[];
  };
}

const PropertyHero: React.FC<PropertyHeroProps> = ({ property }) => {
  const heroImage = property.images?.[0] ?? null;
  const location = [property.address.city, property.address.state, property.address.country]
    .filter(Boolean)
    .join(', ');

  return (
    <div className="relative w-full">
      {/* Background image */}
      <ImagePlaceholder
        src={heroImage}
        alt={property.name}
        aspectRatio="16:9"
        icon="hotel"
        className="w-full max-h-[480px]"
      />

      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />

      {/* Text overlay */}
      <div className="absolute bottom-0 left-0 right-0 p-6 md:p-10">
        <div className="mx-auto max-w-7xl">
          <StarRating rating={property.starRating} size="md" />
          <h1 className="mt-2 font-display text-3xl font-bold text-white md:text-5xl">
            {property.name}
          </h1>
          <p className="mt-2 flex items-center gap-1.5 text-base text-white/80">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
            </svg>
            {location}
          </p>
        </div>
      </div>
    </div>
  );
};

export default PropertyHero;
