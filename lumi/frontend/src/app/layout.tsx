import type { Metadata, Viewport } from 'next';
import '@/styles/globals.css';
import BottomNav from '@/components/BottomNav';
import AppHeader from '@/components/AppHeader';
import ServiceWorkerRegister from '@/components/ServiceWorkerRegister';
import TokenRefreshProvider from '@/components/TokenRefreshProvider';
import AuthGuard from '@/components/AuthGuard';
import ErrorBoundary from '@/components/ErrorBoundary';

export const metadata: Metadata = {
  title: 'LUMI | StayOS',
  description: 'GM Daily Intelligence Brief - Part of StayOS',
  // LUMI is served under /lumi; static asset URLs in <head>/manifest are not
  // auto-prefixed by basePath, so they carry the /lumi prefix explicitly.
  manifest: '/lumi/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'LUMI',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  viewportFit: 'cover',
  themeColor: '#080c18',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="icon" href="/lumi/favicon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/lumi/icons/icon-192.png" />
      </head>
      <body className="bg-background text-white min-h-screen">
        <ErrorBoundary>
          <AuthGuard>
            <AppHeader />
            <main className="pt-12 pb-16 px-4 max-w-md mx-auto min-h-screen">
              {children}
            </main>
            <BottomNav />
          </AuthGuard>
        </ErrorBoundary>
        <ServiceWorkerRegister />
        <TokenRefreshProvider />
      </body>
    </html>
  );
}
