// LandingPage - the StayOS shell's public marketing view.
//
// Shown to unauthenticated visitors at the site root ("/") before they sign in.
// It explains what StayOS is and details its two live features (LUMI and PULSE),
// then hands off to the login form via the onSignIn callback (the parent shell
// swaps this view for the LoginForm in place - no redirect). The platform story
// and feature copy are grounded in the repo README and the shell feature
// catalog so the marketing page stays consistent with what actually ships.

'use client';

import {
  Sun,
  Zap,
  Layers,
  Database,
  Smartphone,
  Sparkles,
  BarChart3,
  Users,
  Award,
  BriefcaseBusiness,
  type LucideIcon,
} from 'lucide-react';
import StayOSLogo from '@/components/StayOSLogo';

interface LandingPageProps {
  // Swaps the shell to the login form (handled by the parent). Invoked by every
  // "Sign In" call-to-action on the page.
  onSignIn: () => void;
}

// A single live feature (LUMI / PULSE) rendered as a detailed marketing card.
interface LiveFeature {
  id: string;
  name: string;
  tagline: string;
  Icon: LucideIcon;
  // Accent gradient endpoints (Tailwind color tokens) for the feature mark.
  gradientFrom: string;
  gradientTo: string;
  description: string;
  // Three concrete capability bullets shown under the description.
  highlights: string[];
}

// The two shipped features. Copy is derived from the README product vision so
// the landing page never overstates what is live.
const LIVE_FEATURES: LiveFeature[] = [
  {
    id: 'lumi',
    name: 'LUMI',
    tagline: 'Start the day informed',
    Icon: Sun,
    gradientFrom: 'from-warning',
    gradientTo: 'to-accent',
    description:
      'A daily AI-generated brief that pulls the numbers that matter into one screen before the shift starts - so the GM walks the floor already knowing the day.',
    highlights: [
      'KPIs, VIP arrivals, overbooking risk, and out-of-order rooms at a glance',
      'A 60-90 second audio brief for a hands-free start to the morning',
      'Voice and chat Q&A over the same live property data',
    ],
  },
  {
    id: 'pulse',
    name: 'PULSE',
    tagline: 'Stay informed all day',
    Icon: Zap,
    gradientFrom: 'from-tier-critical',
    gradientTo: 'to-accent',
    description:
      'Real-time, tiered alerts pushed the moment a situation develops - so the GM acts 45 minutes early instead of finding out at the front desk.',
    highlights: [
      'Critical / Warning / Info tiers surface what needs attention first',
      'AI triage explains each alert and recommends the next action',
      'Closed-loop resolution: the human approves, the agent executes',
    ],
  },
];

// Why StayOS as a platform - three pillars from the README ("built once and
// shared"). Kept short; the feature cards carry the detail.
const PLATFORM_PILLARS: { Icon: LucideIcon; title: string; body: string }[] = [
  {
    Icon: Database,
    title: 'One data layer',
    body: 'Reads the property\u2019s existing systems (PMS, revenue, loyalty, facilities) through one shared read-only layer - no new integrations per feature.',
  },
  {
    Icon: Sparkles,
    title: 'One AI pipeline',
    body: 'A shared generate-and-validate pipeline turns that data into proactive intelligence, so every feature speaks with the same grounded voice.',
  },
  {
    Icon: Smartphone,
    title: 'One login, on mobile',
    body: 'Sign in once and every feature is a tap away - delivered mobile-first as a dashboard and an audio brief, before you go looking for it.',
  },
];

// The role-specific features still on the roadmap (the shell\u2019s "Coming Soon"
// catalog). Shown as a compact strip to make the platform story concrete.
const UPCOMING_FEATURES: { name: string; Icon: LucideIcon }[] = [
  { name: 'Revenue Optimizer', Icon: BarChart3 },
  { name: 'Guest Experience', Icon: Users },
  { name: 'Best Practice Coach', Icon: Award },
  { name: 'Portfolio Analyzer', Icon: BriefcaseBusiness },
];

export default function LandingPage({ onSignIn }: LandingPageProps) {
  return (
    <div className="flex flex-col items-center py-12">
      {/* Hero: brand lockup + the one-line StayOS promise + primary CTA. */}
      <header className="flex flex-col items-center text-center">
        <StayOSLogo size={64} wordmarkClassName="text-4xl" />
        <p className="text-base text-gray-300 mt-4 max-w-md">
          The operating system for hotel General Managers and associates.
        </p>
        <p className="text-sm text-gray-500 mt-3 max-w-md leading-relaxed">
          Every hotel runs on disconnected systems, so operational intelligence arrives late, in
          fragments, and only if you go looking for it. StayOS reads your property&apos;s existing
          data and turns it into proactive, AI-generated intelligence - delivered to the people who
          run the hotel, on mobile, before they need it.
        </p>

        <button
          type="button"
          onClick={onSignIn}
          className="mt-7 bg-accent text-white font-semibold px-8 py-3 rounded-lg hover:bg-accent/90 transition-colors"
        >
          Sign In
        </button>
        <p className="text-xs text-gray-600 mt-3">Two live features. One login.</p>
      </header>

      {/* Live features: the detailed LUMI + PULSE marketing cards. */}
      <section className="w-full mt-14" aria-labelledby="live-features-heading">
        <h2
          id="live-features-heading"
          className="text-xs font-semibold tracking-widest text-gray-500 uppercase text-center mb-5"
        >
          Live today
        </h2>

        <div className="space-y-4">
          {LIVE_FEATURES.map((feature) => (
            <article
              key={feature.id}
              className="rounded-xl border border-gray-800 bg-surface p-5 shadow-lg shadow-black/20"
            >
              <div className="flex items-center gap-3 mb-3">
                {/* Feature mark: gradient-tinted icon tile. */}
                <div
                  className={`flex items-center justify-center w-11 h-11 rounded-lg bg-gradient-to-br ${feature.gradientFrom} ${feature.gradientTo}`}
                >
                  <feature.Icon size={22} className="text-white" strokeWidth={1.75} aria-hidden />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white leading-none">{feature.name}</h3>
                  <p className="text-xs text-accent mt-1">{feature.tagline}</p>
                </div>
              </div>

              <p className="text-sm text-gray-400 leading-relaxed mb-3">{feature.description}</p>

              <ul className="space-y-1.5">
                {feature.highlights.map((highlight) => (
                  <li key={highlight} className="flex items-start gap-2 text-xs text-gray-400">
                    <span className="mt-1.5 h-1 w-1 flex-shrink-0 rounded-full bg-accent" aria-hidden />
                    <span>{highlight}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      {/* Platform story: one data layer / one AI pipeline / one login. */}
      <section className="w-full mt-14" aria-labelledby="platform-heading">
        <h2
          id="platform-heading"
          className="text-xs font-semibold tracking-widest text-gray-500 uppercase text-center mb-2"
        >
          One platform, not one tool
        </h2>
        <p className="text-sm text-gray-500 text-center max-w-md mx-auto mb-6 leading-relaxed">
          Identity, data, AI, and mobile delivery are built once and shared. New role-specific
          features plug into the same foundation, reading the same data with no new integrations.
        </p>

        <div className="space-y-3">
          {PLATFORM_PILLARS.map((pillar) => (
            <div
              key={pillar.title}
              className="flex items-start gap-3 rounded-lg border border-gray-800/70 bg-surface/60 p-4"
            >
              <pillar.Icon
                size={20}
                className="text-accent mt-0.5 flex-shrink-0"
                strokeWidth={1.5}
                aria-hidden
              />
              <div>
                <p className="text-sm font-semibold text-white">{pillar.title}</p>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">{pillar.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Roadmap strip: the "Coming Soon" role-specific features. */}
      <section className="w-full mt-12" aria-labelledby="roadmap-heading">
        <h2
          id="roadmap-heading"
          className="text-xs font-semibold tracking-widest text-gray-500 uppercase text-center mb-4 flex items-center justify-center gap-2"
        >
          <Layers size={13} aria-hidden />
          More coming
        </h2>
        <div className="grid grid-cols-2 gap-2">
          {UPCOMING_FEATURES.map((feature) => (
            <div
              key={feature.name}
              className="flex items-center gap-2 rounded-lg border border-gray-800/60 bg-surface/40 px-3 py-2.5"
            >
              <feature.Icon size={16} className="text-gray-600 flex-shrink-0" strokeWidth={1.5} aria-hidden />
              <span className="text-xs text-gray-400 truncate">{feature.name}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Closing CTA - repeat the sign-in affordance after the story. */}
      <div className="mt-12 flex flex-col items-center">
        <button
          type="button"
          onClick={onSignIn}
          className="bg-accent text-white font-semibold px-8 py-3 rounded-lg hover:bg-accent/90 transition-colors"
        >
          Sign In
        </button>
      </div>

      {/* Footer - matches the login / grid views. */}
      <footer className="text-center mt-12">
        <p className="text-[10px] text-gray-600">&copy; 2026 Aloha Hotels &amp; Resorts</p>
        <p className="text-[9px] text-gray-700 mt-1 max-w-xs mx-auto">
          Aloha Hotels &amp; Resorts is a fictional brand for demo purposes only.
        </p>
      </footer>
    </div>
  );
}
