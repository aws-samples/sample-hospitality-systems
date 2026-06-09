import { ReactNode, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  BedDouble,
  Sparkles,
  CreditCard,
  Users,
  BarChart3,
  Moon,
  Menu,
  X,
  LogOut,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface LayoutProps {
  children: ReactNode;
}

interface NavItem {
  path: string;
  label: string;
  Icon: LucideIcon;
  roles: string[];
}

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Dashboard', Icon: LayoutDashboard, roles: ['Admin', 'Manager', 'FrontDesk', 'Housekeeping', 'RegionalManager', 'RevenueManager'] },
  { path: '/stays', label: 'Stays', Icon: BedDouble, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { path: '/housekeeping', label: 'Housekeeping', Icon: Sparkles, roles: ['Admin', 'Manager', 'Housekeeping'] },
  { path: '/billing', label: 'Billing', Icon: CreditCard, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { path: '/guests', label: 'Guests', Icon: Users, roles: ['Admin', 'Manager', 'FrontDesk'] },
  { path: '/reports', label: 'Reports', Icon: BarChart3, roles: ['Admin', 'Manager', 'RegionalManager', 'RevenueManager'] },
  { path: '/audit', label: 'Night Audit', Icon: Moon, roles: ['Admin', 'Manager'] },
];

export default function Layout({ children }: LayoutProps) {
  const { user, signOut, groups } = useAuth();
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const visibleNavItems = NAV_ITEMS.filter((item) =>
    item.roles.some((role) => groups.includes(role)),
  );

  // Close drawer on navigation
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // Close drawer on Escape
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  const initial = (user?.email || '?').charAt(0).toUpperCase();

  return (
    <div className="min-h-screen bg-neutral-50 flex" data-testid="pms-layout">
      {/* Backdrop for mobile drawer */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-neutral-900/50 lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        data-testid="pms-sidebar"
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-primary-700 text-white flex flex-col transform transition-transform duration-200 lg:static lg:translate-x-0 ${
          drawerOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        {/* Logo */}
        <div className="px-6 pt-6 pb-5 border-b border-primary-800/60 relative">
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="lg:hidden absolute top-4 right-4 text-white/70 hover:text-white"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
          <h1 className="font-display text-xl font-bold text-white leading-tight">
            AnyCompany
          </h1>
          <p className="font-display text-xs text-white/70 tracking-widest uppercase mt-0.5">
            Hotels &amp; Resorts
          </p>
          <div className="mt-3 h-1 w-12 rounded-full bg-accent-500" />
          <p className="text-xs text-white/60 mt-3">Staff Dashboard</p>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 overflow-y-auto" data-testid="pms-navigation">
          {visibleNavItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.Icon;
            return (
              <Link
                key={item.path}
                to={item.path}
                data-testid={`nav-${item.label.toLowerCase().replace(' ', '-')}`}
                className={`flex items-center gap-3 px-6 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary-800 text-accent-400 border-l-2 border-accent-400 -ml-[2px] pl-[26px]'
                    : 'text-white/80 hover:bg-primary-800/60 hover:text-white'
                }`}
              >
                <Icon className="h-4 w-4 flex-shrink-0" strokeWidth={1.75} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="px-6 py-4 border-t border-primary-800/60">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-9 w-9 rounded-full bg-accent-500 text-white font-semibold flex items-center justify-center flex-shrink-0">
              {initial}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white truncate">{user?.email}</p>
              <p className="text-xs text-white/60 truncate">{groups.join(', ') || 'No role'}</p>
            </div>
          </div>
          <button
            onClick={signOut}
            data-testid="sign-out-button"
            className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-primary-800 hover:text-white transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        {/* Mobile top bar */}
        <header className="lg:hidden sticky top-0 z-20 flex items-center gap-3 bg-white border-b border-neutral-200 px-4 py-3">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="inline-flex items-center justify-center h-9 w-9 rounded-lg text-neutral-700 hover:bg-neutral-100 transition-colors"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="font-display text-base font-semibold text-neutral-900">
            AnyCompany PMS
          </span>
        </header>

        <div className="flex-1 px-4 sm:px-6 lg:px-8 py-6 lg:py-8 max-w-7xl w-full mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
