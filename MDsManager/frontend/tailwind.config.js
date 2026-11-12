/** @type {import('tailwindcss').Config} */
// Токени MDS Connect (style.css :root і :root[data-theme="dark"]) — значення в src/index.css як RGB-канали,
// щоб працювали модифікатори прозорості (bg-brand/5). Див. docs/CONNECT_DESIGN_AUDIT.md.
const c = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // темна тема — як у Connect: <html data-theme="dark">
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: c('brand'), 2: c('brand-2'), ink: c('brand-ink') },
        gold: { DEFAULT: c('gold'), soft: c('gold-soft'), tint: c('gold-tint') },
        bg: c('bg'),
        surface: { DEFAULT: c('surface'), 2: c('surface-2'), 3: c('surface-3') },
        ink: { DEFAULT: c('ink'), 2: c('ink-2'), 3: c('ink-3') },
        line: { DEFAULT: c('line'), strong: c('line-strong') },
        focus: 'rgb(var(--gold) / .35)',
        ok: { DEFAULT: c('ok'), bg: c('ok-bg') },
        warn: { DEFAULT: c('warn'), bg: c('warn-bg') },
        danger: { DEFAULT: c('danger'), bg: c('danger-bg') },
        info: { DEFAULT: c('info'), bg: c('info-bg') },
        prog: { DEFAULT: c('prog'), bg: c('prog-bg') },
        muted: { bg: c('muted-bg') },
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
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow)',
        lg: 'var(--shadow-lg)',
        ring: '0 0 0 3px rgb(var(--gold) / .35)',
        card: 'var(--shadow)',
      },
      transitionTimingFunction: {
        ease: 'cubic-bezier(.2, .7, .2, 1)',
      },
      transitionDuration: {
        1: '120ms',
        2: '200ms',
        3: '320ms',
      },
      keyframes: {
        'rise-in': { from: { opacity: '0', transform: 'translateY(10px)' } },
        fade: { from: { opacity: '0' } },
        pop: { '0%': { transform: 'scale(.85)' }, '60%': { transform: 'scale(1.08)' }, '100%': { transform: 'scale(1)' } },
        shimmer: { from: { backgroundPosition: '-200% 0' }, to: { backgroundPosition: '200% 0' } },
        shake: { '20%, 60%': { transform: 'translateX(-7px)' }, '40%, 80%': { transform: 'translateX(7px)' } },
        'mark-in': { from: { opacity: '0', transform: 'scale(.8) rotate(-8deg)' } },
      },
      animation: {
        'rise-in': 'rise-in .32s cubic-bezier(.2, .7, .3, 1) both',
        fade: 'fade 200ms cubic-bezier(.2, .7, .2, 1)',
        pop: 'pop .3s ease-out',
        shimmer: 'shimmer 1.2s linear infinite',
        shake: 'shake .4s',
        'mark-in': 'mark-in .7s cubic-bezier(.2, .7, .3, 1) both',
      },
      // spacing: шкала Connect (4/8/12/16/20/24/32/40) збігається з типовою шкалою Tailwind (1–10)
    },
  },
  plugins: [],
};
