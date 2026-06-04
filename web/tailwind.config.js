/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },
        /* Button tokens */
        "btn-primary": {
          DEFAULT: "hsl(var(--btn-primary-bg))",
          foreground: "hsl(var(--btn-primary-fg))",
          hover: "hsl(var(--btn-primary-hover))",
        },
        "btn-accent": {
          DEFAULT: "hsl(var(--btn-accent-bg))",
          foreground: "hsl(var(--btn-accent-fg))",
          hover: "hsl(var(--btn-accent-hover))",
        },
        "btn-success": {
          DEFAULT: "hsl(var(--btn-success-bg))",
          foreground: "hsl(var(--btn-success-fg))",
          hover: "hsl(var(--btn-success-hover))",
        },
        "btn-destructive": {
          DEFAULT: "hsl(var(--btn-destructive-bg))",
          foreground: "hsl(var(--btn-destructive-fg))",
          hover: "hsl(var(--btn-destructive-hover))",
        },
        /* Surface tokens */
        "surface-hover": "hsl(var(--surface-hover))",
        "surface-pressed": "hsl(var(--surface-pressed))",
        "surface-subtle": "hsl(var(--surface-subtle))",
        /* Badge tokens */
        "badge-success": {
          bg: "hsl(var(--badge-success-bg))",
          fg: "hsl(var(--badge-success-fg))",
        },
        "badge-destructive": {
          bg: "hsl(var(--badge-destructive-bg))",
          fg: "hsl(var(--badge-destructive-fg))",
        },
        "badge-warning": {
          bg: "hsl(var(--badge-warning-bg))",
          fg: "hsl(var(--badge-warning-fg))",
        },
        "badge-info": {
          bg: "hsl(var(--badge-info-bg))",
          fg: "hsl(var(--badge-info-fg))",
        },
        "badge-neutral": {
          bg: "hsl(var(--badge-neutral-bg))",
          fg: "hsl(var(--badge-neutral-fg))",
        },
        /* Chart/canvas */
        "chart-tooltip": {
          bg: "hsl(var(--chart-tooltip-bg))",
          fg: "hsl(var(--chart-tooltip-fg))",
          border: "hsl(var(--chart-tooltip-border))",
        },
        "chart-axis": "hsl(var(--chart-axis))",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}