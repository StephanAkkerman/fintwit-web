/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Default Tailwind tops out at 2xl (1536px); ultrawide monitors (1920px+,
      // 3440px, ...) need a couple more steps so the layout keeps widening
      // instead of leaving the extra width unused.
      screens: {
        '3xl': '1920px',
        '4xl': '2560px',
      },
    },
  },
  plugins: [],
}