/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      fontFamily: {
        'space': ['Space Grotesk', 'sans-serif'],
        'manrope': ['Manrope', 'sans-serif'],
        'syne': ['Syne', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace']
      },
      colors: {
        obsidian: '#050505',
        charcoal: '#121212',
        slate: '#1E1E22',
        'neon-cyan': '#00F0FF',
        'electric-purple': '#7000FF',
        'signal-green': '#00FF94',
        'deep-indigo': '#1A1B4B',
        'warm-gold': '#FFD700',
        'sunset-orange': '#FF6B6B',
        'text-primary': '#FFFFFF',
        'text-secondary': '#A1A1AA',
        'border-subtle': 'rgba(255, 255, 255, 0.1)',
        'glass-bg': 'rgba(20, 20, 25, 0.7)',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))'
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' }
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      },
      backgroundImage: {
        'hero-glow': 'radial-gradient(circle at 50% 50%, rgba(112, 0, 255, 0.15) 0%, rgba(5, 5, 5, 0) 70%)',
        'active-track': 'linear-gradient(90deg, rgba(0, 240, 255, 0.1) 0%, rgba(0, 240, 255, 0) 100%)'
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
};