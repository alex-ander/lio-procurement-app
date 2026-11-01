'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { auth, organizations, type AuthUser, type MemberRole } from '@/lib/api';
import DashboardNav from './components/DashboardNav';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [role, setRole] = useState<MemberRole | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const { user } = await auth.me();
        setUser(user);
        try {
          const org = await organizations.getMine();
          setRole(org.role);
        } catch {
          // Not part of an organization (yet) — nav falls back to basics.
          setRole(null);
        }
      } catch {
        router.push('/sign-in');
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-accent-deep"></div>
      </div>
    );
  }

  if (!user) {
    return null; // Will redirect
  }

  return (
    <div className="min-h-screen bg-canvas">
      <DashboardNav user={user} role={role} />
      <main className="pt-16">
        {children}
      </main>
    </div>
  );
}
