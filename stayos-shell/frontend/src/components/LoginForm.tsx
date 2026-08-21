// LoginForm - the StayOS shell's unauthenticated view.
//
// Authenticates against the shared StayOS (LUMI) Cognito user pool. On invalid
// credentials the GM is retained on this prompt and a visible error is shown; on
// success the parent shell flips to the feature grid (no redirect). Mirrors the
// StayOS branding used by the LUMI/PULSE login pages.

'use client';

import { useState } from 'react';
import StayOSLogo from '@/components/StayOSLogo';

interface LoginFormProps {
  // Delegated to the shell auth hook; resolves once Cognito responds.
  onSubmit: (email: string, password: string) => void | Promise<void>;
  loading: boolean;
  error: string | null;
}

export default function LoginForm({ onSubmit, loading, error }: LoginFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await onSubmit(email, password);
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      {/* StayOS logo lockup */}
      <StayOSLogo size={64} wordmarkClassName="text-3xl" />
      <p className="text-sm text-gray-400 mb-1 mt-3">The Operating System for Hotel Associates</p>
      <p className="text-xs text-gray-500 mb-8">Sign in once to access every feature</p>

      <form onSubmit={handleSubmit} className="w-full max-w-xs space-y-4">
        <label className="sr-only" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="w-full bg-surface border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-accent"
          required
          autoComplete="email"
        />

        <label className="sr-only" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="w-full bg-surface border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-accent"
          required
          autoComplete="current-password"
        />

        {/* Visible credentials error indication. */}
        {error && (
          <p role="alert" className="text-danger text-sm text-center">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-accent text-white font-semibold py-3 rounded-lg hover:bg-accent/90 transition-colors disabled:opacity-50"
        >
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>

      <p className="text-[10px] text-gray-600 mt-8">&copy; 2026 Aloha Hotels &amp; Resorts</p>
      <p className="text-[9px] text-gray-700 mt-1 text-center max-w-xs">
        Aloha Hotels &amp; Resorts is a fictional brand for demo purposes only.
      </p>
    </div>
  );
}
