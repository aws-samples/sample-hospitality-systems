import React from 'react';
import ImagePlaceholder from '../common/ImagePlaceholder';

interface ImageGalleryProps {
  images?: string[] | null;
  propertyName: string;
}

const ImageGallery: React.FC<ImageGalleryProps> = ({ images, propertyName }) => {
  const safeImages = images ?? [];

  if (safeImages.length === 0) {
    return (
      <div className="overflow-hidden rounded-xl">
        <ImagePlaceholder
          src={null}
          alt={propertyName}
          aspectRatio="16:9"
          icon="hotel"
          className="w-full"
        />
      </div>
    );
  }

  const mainImage = safeImages[0];
  const sideImages = safeImages.slice(1, 5);

  return (
    <div className="grid grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-xl" style={{ maxHeight: 420 }}>
      {/* Large main image */}
      <div className="col-span-2 row-span-2">
        <ImagePlaceholder
          src={mainImage}
          alt={`${propertyName} - Main`}
          aspectRatio="1:1"
          icon="hotel"
          className="h-full w-full"
        />
      </div>

      {/* 4 smaller images */}
      {sideImages.map((img, idx) => (
        <div key={idx} className="col-span-1 row-span-1">
          <ImagePlaceholder
            src={img}
            alt={`${propertyName} - ${idx + 2}`}
            aspectRatio="1:1"
            icon="hotel"
            className="h-full w-full"
          />
        </div>
      ))}

      {/* Fill remaining slots with placeholders if fewer than 4 side images */}
      {Array.from({ length: Math.max(0, 4 - sideImages.length) }).map((_, idx) => (
        <div key={`placeholder-${idx}`} className="col-span-1 row-span-1">
          <ImagePlaceholder
            src={null}
            alt={`${propertyName} - Photo`}
            aspectRatio="1:1"
            icon="hotel"
            className="h-full w-full"
          />
        </div>
      ))}
    </div>
  );
};

export default ImageGallery;
