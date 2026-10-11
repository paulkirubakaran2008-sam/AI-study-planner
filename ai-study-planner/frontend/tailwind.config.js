/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bricolage Grotesque Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ['"Figtree Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        sunken: "rgb(var(--sunken) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        primary: "rgb(var(--primary) / <alpha-value>)",
        "primary-ink": "rgb(var(--primary-ink) / <alpha-value>)",
        soft: "rgb(var(--soft) / <alpha-value>)",
        amber: "rgb(var(--amber) / <alpha-value>)",
        crit: "rgb(var(--crit) / <alpha-value>)",
        high: "rgb(var(--high) / <alpha-value>)",
        med: "rgb(var(--med) / <alpha-value>)",
        low: "rgb(var(--low) / <alpha-value>)",
      },
      borderRadius: { xl: "0.875rem" },
      boxShadow: { card: "0 1px 0 rgb(var(--line) / 0.6), 0 8px 24px -16px rgb(var(--shadow) / 0.25)" },
    },
  },
  plugins: [],
};
