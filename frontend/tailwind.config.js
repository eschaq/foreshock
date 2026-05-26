/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand palette from CLAUDE.md §8 — wired as semantic tokens so
        // the step-8 reskin can swap values without touching components.
        base: "#0A0C12",
        surface: "#161B2B",
        signal: {
          blue: "#3B82F6",
          teal: "#3FB8AF",
          amber: "#FFAA33",
          red: "#FF5247",
        },
        ink: {
          primary: "#EEF1F8",
          muted: "#9AA3B8",
          dim: "#5A6178",
        },
      },
    },
  },
  plugins: [],
};
