/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#070b14',
          900: '#0d1117',
          800: '#131c2e',
          700: '#1a2540',
          600: '#243352',
        },
        accent: {
          DEFAULT: '#16c784',
          dark: '#0fa36a',
          light: '#4dd9a0',
        },
        amber: {
          cricket: '#f59e0b',
        },
        stat: '#e2e8f0',
      },
      fontFamily: {
        display: ['Barlow Condensed', 'Oswald', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': '0.65rem',
      },
    },
  },
  plugins: [],
}
