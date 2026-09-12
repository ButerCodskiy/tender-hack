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
        mos: {
          red: {
            DEFAULT: '#db2b21',
            hover: '#cd1f15',
            focus: '#c7160c',
            active: '#af221a',
            light: '#fef0ef',
          },
          blue: {
            DEFAULT: '#264b82',
            hover: '#1c3f72',
            focus: '#163769',
            active: '#1a345b',
            light: '#eaf6ff',
          },
          ink: {
            DEFAULT: '#1a1a1a',
            secondary: '#272727',
            muted: '#7f8792',
            disabled: '#9ba1a9',
          },
          canvas: '#f7f8f9',
          surface: '#ffffff',
          border: 'rgba(34, 36, 38, 0.15)',
          hairline: '#e5e5e5',
          table: '#dddddd',
          success: {
            DEFAULT: '#0d9b68',
            hover: '#05895a',
            active: '#096c48',
            light: '#e7f8f2',
          },
          warning: {
            DEFAULT: '#fbbd08',
            hover: '#eaae00',
            light: '#fffbe6',
          },
          alert: {
            DEFAULT: '#f67319',
            hover: '#f66400',
            light: '#fff3ec',
          }
        },
        primary: {
          50: '#fef0ef',
          100: '#fde1df',
          200: '#fbc3bf',
          300: '#f7968f',
          400: '#f1655b',
          500: '#db2b21',
          600: '#cd1f15',
          700: '#af221a',
        },
        title: {
          50: '#1a1a1a',
        },
        text: {
          50: '#1a1a1a',
          100: '#7f8792',
          200: '#555555',
        },
        background: {
          50: '#ffffff',
          100: '#ffffff',
          soft: {
            50: '#f7f8f9',
            100: '#f2f7fc',
            200: '#eaf6ff',
          }
        },
        base: {
          50: '#e5e5e5',
          100: '#dddddd',
          200: '#d4d4d5',
        },
        foreground: {
          soft: {
            500: '#555555',
          }
        }
      },
      fontFamily: {
        sans: ['Open Sans', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        secondary: ['Nunito Sans', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        'none': '0px',
        'subtle': '1px',
        'sm': '2px',
        'md': '4px',
      },
      maxWidth: {
        'portal-lg': '1327px',
        'portal-md': '933px',
        'portal-sm': '723px',
      }
    },
  },
  plugins: [],
}
