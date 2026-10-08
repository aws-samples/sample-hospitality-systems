import React from 'react';

interface ImagePlaceholderProps {
  src?: string | null;
  alt: string;
  aspectRatio?: '16:9' | '4:3' | '3:2' | '1:1';
  className?: string;
  icon?: 'hotel' | 'room' | 'pool' | 'restaurant';
}

const aspectClasses: Record<string, string> = {
  '16:9': 'aspect-video',
  '4:3': 'aspect-4/3',
  '3:2': 'aspect-3/2',
  '1:1': 'aspect-square',
};

const PlaceholderIcon: React.FC<{ icon: ImagePlaceholderProps['icon'] }> = ({ icon }) => {
  const cls = 'w-12 h-12 text-white/40';

  switch (icon) {
    case 'room':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M2 20h20M4 20V9l8-5 8 5v11M9 20v-5h6v5M9 12h.01M15 12h.01" />
        </svg>
      );
    case 'pool':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M2 18c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1 2.5-1 4-1M2 22c1.5 0 2.5-1 4-1s2.5 1 4 1 2.5-1 4-1 2.5 1 4 1 2.5-1 4-1M8 6a2 2 0 100-4 2 2 0 000 4zM6 8v6M10 8v6" />
        </svg>
      );
    case 'restaurant':
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v6m0 0a3 3 0 003-3V3m-3 6a3 3 0 01-3-3V3m3 18v-9m6-6v3a3 3 0 01-3 3h0m-6 0h0a3 3 0 01-3-3V3" />
        </svg>
      );
    case 'hotel':
    default:
      return (
        <svg className={cls} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
        </svg>
      );
  }
};

const ImagePlaceholder: React.FC<ImagePlaceholderProps> = ({
  src,
  alt,
  aspectRatio = '16:9',
  className = '',
  icon = 'hotel',
}) => {
  const aspect = aspectClasses[aspectRatio];

  if (src) {
    return (
      <div className={`overflow-hidden ${aspect} ${className}`}>
        <img
          src={src}
          alt={alt}
          loading="lazy"
          className="h-full w-full object-cover"
        />
      </div>
    );
  }

  return (
    <div
      className={`flex items-center justify-center bg-linear-to-br from-primary-600 to-primary-900 ${aspect} ${className}`}
      role="img"
      aria-label={alt}
    >
      <div className="flex flex-col items-center gap-2">
        <PlaceholderIcon icon={icon} />
        <span className="text-xs text-white/30 font-medium tracking-wide uppercase">
          {alt}
        </span>
      </div>
    </div>
  );
};

export default ImagePlaceholder;
