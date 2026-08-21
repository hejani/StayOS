'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowLeft, Settings } from 'lucide-react';
import { withBase } from '@/lib/constants';

interface AppHeaderProps {
  propertyName?: string;
}

export default function AppHeader({ propertyName }: AppHeaderProps) {
  const pathname = usePathname();

  // Hide header on login page
  if (pathname.startsWith('/login')) return null;

  return (
    <header className="fixed top-0 left-0 right-0 bg-background/95 backdrop-blur-sm border-b border-gray-800 pt-[var(--sat)] z-50">
      {/* 3-column grid so the LUMI logo is truly centered in the bar regardless
          of the left (back link) and right (settings) widths. */}
      <div className="grid grid-cols-3 items-center h-12 px-4 max-w-md mx-auto">
        {/* Left: back to the StayOS shell (feature launcher). The shell lives at
            the site root "/", OUTSIDE LUMI's "/lumi" basePath, so this is a raw
            <a href="/"> (next/link would stay under /lumi). It does NOT sign out
            - the shared session persists, so the shell shows the feature grid and
            the GM can switch to PULSE without re-authenticating. */}
        <div className="justify-self-start">
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- "/" is
              the StayOS shell, outside LUMI's /lumi basePath, not an internal page. */}
          <a
            href="/"
            aria-label="Back to StayOS"
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors rounded-full px-1.5 py-1 hover:bg-surface"
          >
            <ArrowLeft size={14} aria-hidden />
            <span>StayOS</span>
          </a>
        </div>

        {/* Center: LUMI compact logo, links to LUMI home. Plain <img> (not
            next/image): with `unoptimized` static export, next/image emits the
            src verbatim and does NOT apply basePath, so the asset is referenced
            with the /lumi prefix explicitly via withBase(). */}
        <Link href="/" className="justify-self-center" aria-label="LUMI home">
          {/* eslint-disable-next-line @next/next/no-img-element -- static export;
              basePath-prefixed SVG served from S3/CloudFront, no optimizer. */}
          <img src={withBase('/logo-compact.svg')} alt="LUMI" width={100} height={34} />
        </Link>

        {/* Right: property chip + settings icon */}
        <div className="justify-self-end flex items-center gap-2">
          {propertyName && (
            <span className="text-xs text-gray-400 bg-surface px-2 py-1 rounded-full truncate max-w-[140px]">
              {propertyName}
            </span>
          )}
          <Link
            href="/settings/"
            className="p-2 text-gray-400 hover:text-white transition-colors"
            aria-label="Settings"
          >
            <Settings size={20} strokeWidth={1.5} />
          </Link>
        </div>
      </div>
    </header>
  );
}
