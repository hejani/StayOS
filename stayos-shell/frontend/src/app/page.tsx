// StayOS shell root page ("/").
//
// The single StayOS entry point: shows the login form when unauthenticated and
// the feature launcher grid when authenticated. Sign-in establishes the shared
// StayOS session (localStorage on the shared origin), after which LUMI (/lumi)
// and PULSE (/pulse) read that same session with no second login (SSO).

'use client';

import { useShellAuth } from '@/hooks/useShellAuth';
import LoginForm from '@/components/LoginForm';
import FeatureGrid from '@/components/FeatureGrid';

export default function ShellPage() {
  const { isLoggedIn, user, loading, error, login, logout } = useShellAuth();

  // Brief loading state while the initial session check resolves, so an already
  // authenticated GM does not see a flash of the login form.
  if (loading && !isLoggedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-pulse text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (isLoggedIn) {
    return <FeatureGrid email={user?.email} onLogout={logout} />;
  }

  return <LoginForm onSubmit={login} loading={loading} error={error} />;
}
