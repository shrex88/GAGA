/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#050914',
          900: '#0a1020',
          850: '#0f172a',
          800: '#162038',
          700: '#1e2c4a',
        },
      },
    },
  },
  plugins: [],
}
