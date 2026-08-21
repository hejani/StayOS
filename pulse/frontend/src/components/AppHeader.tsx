// AppHeader - fixed top bar for the PULSE PWA.
//
// Mirrors LUMI's header layout (fixed, safe-area aware, max-w-md) but renders the
// PULSE gradient wordmark instead of a logo image. Hidden on the login page. An
// optional property chip shows the active property, and a Logout control cleanly
// ends the session and returns to the StayOS shell.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowLeft, LogOut } from 'lucide-react';
import { signOut } from '@/lib/auth';

interface AppHeaderProps {
  propertyName?: string;
}

export default function AppHeader({ propertyName }: AppHeaderProps) {
  const pathname = usePathname();

  // Hide the header on the login page.
  if (pathname.startsWith('/login')) return null;

  // Cleanly end the session: clear the Cognito tokens, then hard-navigate to the
  // StayOS root ("/"). The StayOS landing (which shows BOTH LUMI and PULSE) lives
  // at the site root, OUTSIDE PULSE's "/pulse" basePath, so this is a raw
  // window.location assignment to "/" (next/router/withBase would stay under
  // /pulse). A full-page load also guarantees all in-memory app state is dropped.
  const handleLogout = () => {
    signOut();
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  };

  return (
    <header className="fixed top-0 left-0 right-0 bg-background/95 backdrop-blur-sm border-b border-gray-800 pt-[var(--sat)] z-50">
      {/* 3-column grid so the PULSE wordmark is truly centered in the bar
          regardless of the left (back link) and right (logout) widths. */}
      <div className="grid grid-cols-3 items-center h-12 px-4 max-w-md mx-auto">
        {/* Left: back to the StayOS shell (feature launcher). The shell lives at
            the site root "/", OUTSIDE PULSE's "/pulse" basePath, so this is a raw
            <a href="/"> (next/link would stay under /pulse). It does NOT sign out
            - the shared session persists, so the shell shows the feature grid and
            the GM can switch to LUMI without re-authenticating. */}
        <div className="justify-self-start">
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- "/" is
              the StayOS shell, outside PULSE's /pulse basePath, not an internal page. */}
          <a
            href="/"
            aria-label="Back to StayOS"
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors rounded-full px-1.5 py-1 hover:bg-surface"
          >
            <ArrowLeft size={14} aria-hidden />
            <span>StayOS</span>
          </a>
        </div>

        {/* Center: PULSE wordmark - links to the default PULSE view */}
        <Link href="/" className="justify-self-center flex items-center gap-1.5" aria-label="PULSE home">
          <span aria-hidden className="text-lg leading-none">&#9889;</span>
          <span className="text-lg font-black tracking-tight bg-gradient-to-r from-tier-critical via-tier-warning to-tier-info bg-clip-text text-transparent">
            PULSE
          </span>
        </Link>

        {/* Right: optional property chip + Logout */}
        <div className="justify-self-end flex items-center gap-2">
          {propertyName && (
            <span className="text-xs text-gray-400 bg-surface px-2 py-1 rounded-full truncate max-w-[120px]">
              {propertyName}
            </span>
          )}

          {/* Logout - ends the session and returns to the StayOS shell */}
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Log out"
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors rounded-full px-2 py-1 hover:bg-surface"
          >
            <LogOut size={14} aria-hidden />
            <span>Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
}
