/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#e8edf4',
          100: '#c5d1e3',
          200: '#9eb3d0',
          300: '#7795bd',
          400: '#597eaf',
          500: '#3b67a1',
          600: '#1e3a5f',
          700: '#1a3253',
          800: '#152a46',
          900: '#0f1f33',
          950: '#091422',
        },
        accent: {
          50: '#faf6ee',
          100: '#f2e8d0',
          200: '#e6d4a8',
          300: '#d9bf80',
          400: '#d1b177',
          500: '#c9a96e',
          600: '#b8944f',
          700: '#9a7a3e',
          800: '#7c6232',
          900: '#5e4a26',
          950: '#3f3119',
        },
        neutral: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
          950: '#030712',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Playfair Display', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
};
