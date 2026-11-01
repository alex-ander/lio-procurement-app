'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { auth, organizations, ApiError } from '@/lib/api';
import { Button, Input, Alert } from '@/components/base';
import { Logo } from '@/components/Logo';

export default function SignUpPage() {
  const router = useRouter();
  const [step, setStep] = useState<'account' | 'organization'>('account');
  
  // Account details
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Organization details
  const [orgName, setOrgName] = useState('');
  const [orgSlug, setOrgSlug] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Auto-generate slug from org name (invisible to user)
  const handleOrgNameChange = (name: string) => {
    setOrgName(name);
    // Auto-generate slug: "Kongsbak Solutions" -> "kongsbak-solutions"
    const slug = name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
      .substring(0, 50); // Limit length
    setOrgSlug(slug);
  };

  const handleAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Sign up — the returned token is stored, so the user is signed in
      await auth.signUp({ email, password, fullName });
      setStep('organization');
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign up');
      setLoading(false);
    }
  };

  const handleOrganizationSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Generate slug if not already set
    const finalSlug = orgSlug || orgName.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

    try {
      await organizations.create({ name: orgName, slug: finalSlug });
      setSuccess('Account and organization created! Redirecting...');
      setTimeout(() => {
        router.push('/dashboard');
        router.refresh();
      }, 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create organization');
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

        {/* Sign Up Card */}
        <div className="bg-white rounded-2xl shadow-2xl shadow-black/40 p-8">
          {/* Progress Indicator */}
          <div className="flex items-center justify-center mb-6">
            <div className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === 'account'
                    ? 'bg-ink text-white'
                    : 'bg-accent-deep text-white'
                }`}
              >
                {step === 'account' ? '1' : '✓'}
              </div>
              <div className="w-16 h-1 bg-line mx-2">
                <div
                  className={`h-full ${
                    step === 'organization' ? 'bg-ink' : 'bg-line'
                  } transition-all`}
                />
              </div>
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === 'organization'
                    ? 'bg-ink text-white'
                    : 'bg-ink-800/[0.06] text-ink/50'
                }`}
              >
                2
              </div>
            </div>
          </div>

          {error && (
            <Alert variant="error" className="mb-4">
              {error}
            </Alert>
          )}

          {success && (
            <Alert variant="success" className="mb-4">
              {success}
            </Alert>
          )}

          {/* Step 1: Account Creation */}
          {step === 'account' && (
            <>
              <h2 className="text-2xl font-semibold tracking-tight text-ink mb-1">
                Create your account
              </h2>
              <p className="text-ink/50 mb-6 text-sm">Step 1 of 2</p>

              <form onSubmit={handleAccountSubmit} className="space-y-4">
                <Input
                  label="Full Name"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="John Doe"
                  required
                  disabled={loading}
                />

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
                  helperText="Minimum 6 characters"
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading}
                  loading={loading}
                >
                  {loading ? 'Creating account...' : 'Continue'}
                </Button>
              </form>
            </>
          )}

          {/* Step 2: Organization Setup */}
          {step === 'organization' && (
            <>
              <h2 className="text-2xl font-semibold tracking-tight text-ink mb-1">
                Create your organization
              </h2>
              <p className="text-ink/50 mb-6 text-sm">Step 2 of 2</p>

              <form onSubmit={handleOrganizationSubmit} className="space-y-4">
                <Input
                  label="Organization Name"
                  type="text"
                  value={orgName}
                  onChange={(e) => handleOrgNameChange(e.target.value)}
                  placeholder="Acme Corporation"
                  required
                  disabled={loading}
                  helperText="The name of your company or team"
                />

                <Button
                  type="submit"
                  className="w-full"
                  disabled={loading || !orgName.trim()}
                  loading={loading}
                >
                  {loading ? 'Creating organization...' : 'Complete Setup'}
                </Button>
              </form>
            </>
          )}

          <div className="mt-6 text-center text-sm text-ink/55">
            Already have an account?{' '}
            <Link
              href="/sign-in"
              className="text-accent-deep hover:underline font-medium"
            >
              Sign in
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

