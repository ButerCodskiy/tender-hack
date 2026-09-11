/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff3ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#91aeff',
          400: '#5e84fc',
          500: '#3758f9',
          600: '#2544e3',
          700: '#1d35be',
        },
        title: {
          50: '#1f2937',
        },
        text: {
          50: '#374151',
          100: '#6b7280',
          200: '#4b5563',
        },
        background: {
          50: '#ffffff',
          100: '#ffffff',
          soft: {
            50: '#f9fafb',
            100: '#f3f4f6',
            200: '#e5e7eb',
          }
        },
        base: {
          50: '#e5e7eb',
          100: '#e5e7eb',
          200: '#d1d5db',
        },
        foreground: {
          soft: {
            500: '#374151',
          }
        }
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      maxWidth: {
        '184': '46rem',
        '200': '50rem',
      }
    },
  },
  plugins: [],
}
