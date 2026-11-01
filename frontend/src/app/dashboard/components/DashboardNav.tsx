'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { auth, type MemberRole } from '@/lib/api';
import { Button } from '@/components/base';
import { Logo } from '@/components/Logo';

interface DashboardNavProps {
  user: {
    id: string;
    email?: string;
  };
  role: MemberRole | null;
}

export default function DashboardNav({ user, role }: DashboardNavProps) {
  const pathname = usePathname();
  const router = useRouter();

  const handleSignOut = () => {
    auth.signOut();
    router.push('/sign-in');
    router.refresh();
  };

  const navItems = [
    { href: '/dashboard', label: 'Overview' },
    { href: '/dashboard/requests', label: 'Requests' },
    { href: '/dashboard/new-request', label: 'New Request' },
    // Buyers and admins review pending requests.
    ...(role === 'buyer' || role === 'admin'
      ? [{ href: '/dashboard/approvals', label: 'Approvals' }]
      : []),
    { href: '/dashboard/suppliers', label: 'Suppliers' },
    { href: '/dashboard/articles', label: 'Articles' },
    // Members, invites, and settings are managed by admins.
    ...(role === 'admin'
      ? [{ href: '/dashboard/organization', label: 'Organization' }]
      : []),
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 bg-ink border-b border-white/[0.06] z-50">
      <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center">
            <Link href="/dashboard">
              <Logo variant="light" className="h-7" />
            </Link>
          </div>

          {/* Nav Links */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const isActive =
                item.href === '/dashboard'
                  ? pathname === item.href
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3.5 py-2 rounded-full text-sm font-medium tracking-tight transition-colors ${
                    isActive
                      ? 'bg-white/10 text-white'
                      : 'text-white/60 hover:bg-white/[0.06] hover:text-white'
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>

          {/* User Menu */}
          <div className="flex items-center gap-4">
            <span className="text-white/45 text-sm hidden sm:block">
              {user.email}
              {role && <span className="text-white/25"> · {role}</span>}
            </span>
            <Button onClick={handleSignOut} variant="outline" size="sm"
              className="!bg-white/[0.06] !border-white/15 !text-white hover:!bg-white/10">
              Sign Out
            </Button>
          </div>
        </div>
      </div>
    </nav>
  );
}
