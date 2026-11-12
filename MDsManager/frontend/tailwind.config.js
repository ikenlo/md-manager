/** @type {import('tailwindcss').Config} */
// Токени 1-в-1 з MDS Connect (style.css :root) — див. docs/CONNECT_DESIGN_AUDIT.md
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#14392c', 2: '#1d4d3b', ink: '#f5f1e6' },
        gold: { DEFAULT: '#b48a3e', soft: '#e8d4a6', tint: '#f7efdc' },
        bg: '#f4f3ee',
        surface: { DEFAULT: '#ffffff', 2: '#f8f7f3', 3: '#efede6' },
        ink: { DEFAULT: '#23262b', 2: '#4b5058', 3: '#868b93' },
        line: { DEFAULT: '#e4e1d8', strong: '#d3cfc3' },
        focus: 'rgba(180, 138, 62, .35)',
        ok: { DEFAULT: '#1f8a5b', bg: '#e5f4ec' },
        warn: { DEFAULT: '#b7791f', bg: '#fbf0dc' },
        danger: { DEFAULT: '#c2453d', bg: '#fbe7e5' },
        info: { DEFAULT: '#2f6fb3', bg: '#e6eef8' },
        prog: { DEFAULT: '#7c4dcc', bg: '#f0eafb' },
        muted: { bg: '#eeede8' },
      },
      fontFamily: {
        sans: ['Manrope', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'],
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      fontSize: {
        micro: '9.5px',
        '2xs': '11px',
      },
      borderRadius: {
        xs: '6px',
        sm: '8px',
        md: '10px',
        lg: '12px',
        xl: '16px',
        pill: '999px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(20, 30, 25, .06)',
        DEFAULT: '0 1px 2px rgba(20, 30, 25, .04), 0 4px 18px rgba(20, 30, 25, .07)',
        lg: '0 18px 50px rgba(15, 25, 20, .18)',
        ring: '0 0 0 3px rgba(180, 138, 62, .35)',
        card: '0 1px 2px rgba(20, 30, 25, .04), 0 4px 18px rgba(20, 30, 25, .07)',
      },
      transitionTimingFunction: {
        ease: 'cubic-bezier(.2, .7, .2, 1)',
      },
      transitionDuration: {
        1: '120ms',
        2: '200ms',
        3: '320ms',
      },
      // spacing: шкала Connect (4/8/12/16/20/24/32/40) збігається з типовою шкалою Tailwind (1–10)
    },
  },
  plugins: [],
};
