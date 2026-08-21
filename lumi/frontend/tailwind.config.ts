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
        accent: '#6b8fff',
        'accent-secondary': '#9c7cff',
        success: '#2dd4a0',
        warning: '#f5a623',
        danger: '#ff5f6d',
        'tier-ambassador': '#f5a623',
        'tier-titanium': '#9ca3af',
        'tier-platinum': '#6b8fff',
      },
    },
  },
  plugins: [],
};

export default config;
