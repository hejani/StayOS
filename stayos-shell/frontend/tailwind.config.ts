import type { Config } from 'tailwindcss';

// StayOS shell theme. Mirrors LUMI's palette (the shell shares the StayOS visual
// identity) plus the PULSE tier accent colors used on the PULSE feature card.
const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: '#080c18',
        surface: '#0f1526',
        accent: '#6b8fff',
        'accent-secondary': '#9c7cff',
        success: '#2dd4a0',
        warning: '#f5a623',
        danger: '#ff5f6d',
        // PULSE tier colors (used by the PULSE feature card wordmark gradient).
        'tier-critical': '#ff5f6d',
        'tier-warning': '#f5a623',
        'tier-info': '#6b8fff',
      },
    },
  },
  plugins: [],
};

export default config;
