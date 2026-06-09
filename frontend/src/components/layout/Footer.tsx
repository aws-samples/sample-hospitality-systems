import { Link } from 'react-router-dom';

const Footer: React.FC = () => {
  return (
    <footer className="bg-primary-600 text-white">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
          {/* Brand */}
          <div>
            <span className="font-display text-xl font-bold tracking-wide">
              ANYCOMPANY
            </span>
            <span className="ml-0.5 mt-0.5 block h-0.5 w-8 bg-accent-500 rounded-full" />
            <p className="mt-4 text-sm text-white/70 leading-relaxed">
              Exceptional stays at world-class destinations. Experience luxury,
              comfort, and unforgettable hospitality.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-white/90">
              Explore
            </h3>
            <ul className="space-y-2">
              {[
                { label: 'Properties', to: '/properties' },
                { label: 'Search Availability', to: '/search' },
              ].map((link) => (
                <li key={link.to}>
                  <Link
                    to={link.to}
                    className="text-sm text-white/60 transition-colors hover:text-white"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="mt-10 border-t border-white/10 pt-6">
          <p className="text-xs text-white/50">
            &copy; 2026 AnyCompany Hotel &amp; Resorts. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
