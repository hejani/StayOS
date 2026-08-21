// FeatureGrid - the StayOS shell's authenticated view (the launcher).
//
// Renders the StayOS feature catalog. Active cards are raw anchors to the
// feature app on the shared origin (LUMI at /lumi/, PULSE at /pulse/) - full
// navigations that cross Next basePath boundaries, so plain <a> is correct here
// (next/link would keep the shell's routing context). Because the session lives
// in shared origin storage, the target feature reads it directly with no second
// login (SSO). Inactive cards render as disabled "Coming Soon" tiles. A Logout
// control clears the shared session and returns to the login view.

'use client';

import { useRef, useState } from 'react';
import { LogOut, Compass } from 'lucide-react';
import { FEATURES } from '@/lib/features';
import StayOSLogo from '@/components/StayOSLogo';
import OnboardingTour from '@/components/OnboardingTour';
import { useOnboarding } from '@/hooks/useOnboarding';

interface FeatureGridProps {
  // The signed-in GM's email, shown in the header when available.
  email?: string;
  onLogout: () => void;
}

export default function FeatureGrid({ email, onLogout }: FeatureGridProps) {
  // First-login coachmark gating (per GM, per browser).
  const { showTour, dismissTour } = useOnboarding(email);

  // Manual replay: the header "Take a tour" button flips this so a GM can
  // re-run the coachmark any time, independent of the first-login gate. It is
  // in-memory only, so replaying never touches the persisted seen-flag.
  const [replayTour, setReplayTour] = useState(false);

  // The tour is visible on first login OR when manually replayed.
  const tourVisible = (showTour || replayTour) && !!email;

  // Finishing/skipping clears both the first-login gate (persisting the
  // seen-flag) and the in-memory replay flag.
  const finishTour = () => {
    setReplayTour(false);
    dismissTour();
  };

  // Positioning context for the tour bubble, plus per-card refs the tour
  // anchors to. Only the two shipped features (LUMI, PULSE) are highlighted.
  const gridRef = useRef<HTMLDivElement | null>(null);
  const lumiCardRef = useRef<HTMLAnchorElement | null>(null);
  const pulseCardRef = useRef<HTMLAnchorElement | null>(null);
  const cardRefs: Record<string, React.RefObject<HTMLAnchorElement | null>> = {
    lumi: lumiCardRef,
    pulse: pulseCardRef,
  };

  // Two-step tour copy, grounded in the LUMI/PULSE PRFAQ GM benefits.
  const tourSteps = [
    {
      id: 'lumi',
      targetRef: lumiCardRef,
      title: 'Meet LUMI - your AI morning brief',
      body: 'Before your shift, LUMI pulls your KPIs, VIP arrivals, and action items into one screen plus a 60-90s audio brief. Five minutes of clarity so you walk the floor already knowing your day.',
    },
    {
      id: 'pulse',
      targetRef: pulseCardRef,
      title: 'And PULSE - real-time awareness',
      body: 'PULSE keeps you ahead all day: tiered alerts (Critical, Warning, Info) the moment a situation develops - walk risk, a VIP room not ready, an escalating complaint - so you act 45 minutes early, not at the front desk.',
    },
  ];
  return (
    <div className="relative min-h-screen flex flex-col justify-center py-12">
      {/* Manual tour trigger, floated top-left (mirrors Logout top-right).
          Only shown when signed in (the tour anchors to the LUMI/PULSE cards).
          Re-runs the coachmark from step 1 without affecting the first-login
          seen-flag. Disabled while the tour is already visible to avoid a
          redundant re-trigger. */}
      {email && (
        <button
          type="button"
          onClick={() => setReplayTour(true)}
          disabled={tourVisible}
          aria-label="Take a tour"
          className="absolute top-4 left-0 flex items-center gap-1 text-xs text-accent hover:text-white transition-colors rounded-full px-2 py-1 hover:bg-surface disabled:opacity-40 disabled:pointer-events-none"
        >
          <Compass size={14} aria-hidden />
          <span>Take a tour</span>
        </button>
      )}

      {/* Logout floated top-right so it does not affect the centered header. */}
      <button
        type="button"
        onClick={onLogout}
        aria-label="Log out"
        className="absolute top-4 right-0 flex items-center gap-1 text-xs text-gray-400 hover:text-white transition-colors rounded-full px-2 py-1 hover:bg-surface"
      >
        <LogOut size={14} aria-hidden />
        <span>Logout</span>
      </button>

      {/* Centered StayOS logo lockup + signed-in identity. */}
      <div className="flex flex-col items-center text-center mb-8">
        <StayOSLogo size={56} wordmarkClassName="text-2xl" />
        {email ? (
          <p className="text-xs text-gray-400 mt-2">Signed in as {email}</p>
        ) : (
          <p className="text-sm text-gray-400 mt-2">The Operating System for Hotel Associates</p>
        )}
      </div>

      <p className="text-center text-xs text-gray-500 mb-6">
        Powerful AI features designed for hotels of all sizes
      </p>

      {/* Feature grid */}
      <div ref={gridRef} className="relative grid grid-cols-2 gap-3">
        {FEATURES.map((feature) => {
          const className = `relative text-left rounded-xl border p-4 transition-all block ${
            feature.active
              ? 'bg-surface border-accent/40 hover:border-accent active:scale-[0.98] shadow-lg shadow-accent/5'
              : 'bg-surface/50 border-gray-800 opacity-70 pointer-events-none'
          }`;

          const inner = (
            <>
              <feature.Icon
                size={24}
                className={feature.active ? 'text-accent mb-2' : 'text-gray-600 mb-2'}
                strokeWidth={1.5}
              />
              <p
                className={`text-sm font-semibold mb-1 ${
                  feature.active ? 'text-white' : 'text-gray-400'
                }`}
              >
                {feature.name}
              </p>
              <p className="text-[10px] text-gray-500 line-clamp-2">{feature.description}</p>
              <div className="mt-2">
                {feature.active ? (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-accent/15 text-accent">
                    Available
                  </span>
                ) : (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-800 text-gray-500">
                    Coming Soon
                  </span>
                )}
              </div>
            </>
          );

          // Active features link out to the feature app on the shared origin.
          // A raw <a> is used deliberately (full navigation across basePath).
          if (feature.active && feature.href) {
            return (
              <a
                key={feature.id}
                ref={cardRefs[feature.id]}
                href={feature.href}
                aria-label={feature.name}
                className={className}
              >
                {inner}
              </a>
            );
          }

          return (
            <div key={feature.id} aria-disabled className={className}>
              {inner}
            </div>
          );
        })}

        {/* First-login coachmark. Rendered inside the grid so the bubble's
            absolute position is measured against this positioning context.
            Shown on a GM's first login (showTour) OR when manually replayed via
            the "Take a tour" button (replayTour), and only once an email is
            present. Finishing/skipping routes through finishTour, which persists
            the first-login seen-flag exactly as before. */}
        {tourVisible && (
          <OnboardingTour steps={tourSteps} containerRef={gridRef} onFinish={finishTour} />
        )}
      </div>

      {/* Footer */}
      <div className="text-center mt-8">
        <p className="text-[10px] text-gray-600">&copy; 2026 Aloha Hotels &amp; Resorts</p>
        <p className="text-[9px] text-gray-700 mt-1">
          Aloha Hotels &amp; Resorts is a fictional brand for demo purposes only.
        </p>
      </div>
    </div>
  );
}
