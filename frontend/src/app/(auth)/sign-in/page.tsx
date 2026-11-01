'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { auth } from '@/lib/api';
import { Button, Input, Alert } from '@/components/base';
import { Logo } from '@/components/Logo';

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await auth.signIn({ email, password });
      // Successfully signed in, redirect to dashboard
      router.push('/dashboard');
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setLoading(false);
    }
  };

  return (
    <div className="lio-auth-bg min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo/Brand */}
        <div className="flex flex-col items-center text-center mb-8">
          <Logo variant="light" className="mb-5 scale-125" />
          <p className="text-white/55 text-sm tracking-tight">
            AI-powered procurement management
          </p>
        </div>

        {/* Sign In Card */}
        <div className="bg-white rounded-2xl shadow-2xl shadow-black/40 p-8">
          <h2 className="text-2xl font-semibold tracking-tight text-ink mb-1">Welcome back</h2>
          <p className="text-ink/50 text-sm mb-6">Sign in to your workspace</p>

          {error && (
            <Alert variant="error" className="mb-4">
              {error}
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
              disabled={loading}
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              disabled={loading}
            />

            <Button
              type="submit"
              className="w-full"
              disabled={loading}
              loading={loading}
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>

          <div className="mt-6 text-center text-sm text-ink/55">
            Don&apos;t have an account?{' '}
            <Link
              href="/sign-up"
              className="text-accent-deep hover:underline font-medium"
            >
              Sign up
            </Link>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-white/35 text-xs mt-6 tracking-tight">
          Lio · Procurement, reimagined
        </p>
      </div>
    </div>
  );
}

