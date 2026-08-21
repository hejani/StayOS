// Tailwind design tokens for the PULSE PWA.
// Mirrors LUMI's dark StayOS palette (background/surface/accent/success/warning/
// danger) so PULSE feels like part of the same product, and adds PULSE-specific
// alert-tier tokens (tier-critical/tier-warning/tier-info) used by the tier
// filter, alert cards, and triage modal. Colors are drawn from the PULSE
// prototype and the shared StayOS tokens.
import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#080c18',
        surface: '#0f1526',
        'surface-2': '#1a2038',
        accent: '#6b8fff',
        'accent-secondary': '#9c7cff',
        success: '#2dd4a0',
        warning: '#f5a623',
        danger: '#ff5f6d',
        // Alert-tier tokens: CRITICAL maps to danger, WARNING to warning,
        // INFO to accent, matching the prototype's tier colors.
        'tier-critical': '#ff5f6d',
        'tier-warning': '#f5a623',
        'tier-info': '#6b8fff',
      },
      keyframes: {
        'slide-up': {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'slide-up': 'slide-up 0.22s ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
