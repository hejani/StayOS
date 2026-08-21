import type { Metadata, Viewport } from 'next';
import '@/styles/globals.css';

// StayOS shell metadata. The shell is the StayOS entry point (login + feature
// launcher) served at the site root.
export const metadata: Metadata = {
  title: 'StayOS',
  description: 'The Operating System for Hotel Associates',
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
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="bg-background text-white min-h-screen">
        <main className="px-4 w-full max-w-lg mx-auto min-h-screen">{children}</main>
      </body>
    </html>
  );
}
