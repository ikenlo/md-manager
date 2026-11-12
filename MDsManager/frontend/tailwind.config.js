/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#14392c', 2: '#1d4d3b', ink: '#f5f1e6' },
        gold: { DEFAULT: '#b48a3e', soft: '#e8d4a6', tint: '#f7efdc' },
        bg: '#f4f3ee',
        surface: { DEFAULT: '#ffffff', 2: '#f8f7f3' },
        ink: { DEFAULT: '#23262b', 2: '#4b5058', 3: '#868b93' },
        line: '#e7e4da',
      },
      fontFamily: {
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(20,57,44,.04), 0 8px 24px rgba(20,57,44,.06)',
      },
    },
  },
  plugins: [],
};
