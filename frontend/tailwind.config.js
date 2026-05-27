/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Primary family (DESIGN.md): General Sans, self-hosted from
        // /public/fonts/general-sans/. The Tailwind default `font-sans`
        // utility resolves here and is inherited by `html` + `body`.
        sans: [
          "'General Sans'",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "'Segoe UI'",
          "sans-serif",
        ],
        // Mono family — reserved for the FlowPanel event log (terminal-
        // readout genre). Loaded via @fontsource/sometype-mono in main.tsx.
        mono: [
          "'Sometype Mono'",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        // Brand palette anchored to the banner's real pixel values
        // (DESIGN.md § Color). The `signal` family is the only saturated
        // accent palette in the system; everything else is a tinted
        // neutral. Verified WCAG AA against the dark bases (all signal
        // colors >=4.5:1 on #080809 / #0A0C12 / #161B2B).
        base: "#0A0C12",       // page canvas; cool-tinted near-black
        surface: "#161B2B",    // card / panel surface

        // Rule — the single hairline / divider token. Cool-tinted dark
        // blue (220° hue family). Use for: panel borders, table dividers,
        // card outlines, section separators. NEVER pure #fff with alpha.
        rule: "#21263B",

        // Modal scrim tokens. Two strengths only, per DESIGN.md.
        // strong = focused-attention scrim during charged moments.
        // quiet  = post-refresh dimmed scrim so the cards behind become
        //          visible without auto-closing the panel.
        // Both tint toward the base hue (rgb 8,8,9) instead of pure black.
        overlay: {
          strong: "rgba(8, 8, 9, 0.80)",
          quiet:  "rgba(8, 8, 9, 0.30)",
        },

        signal: {
          blue:  "#3B82F6",   // brand / citation anchors / calm waveform
          teal:  "#3FB8AF",   // stable state
          amber: "#FFAA33",   // warning state
          red:   "#FF5247",   // critical state — the rarest color in the system
        },
        ink: {
          primary: "#EEF1F8", // body, wordmark, headings (cool off-white)
          muted:   "#9AA3B8", // secondary text, captions, helpers
          dim:     "#5A6178", // tertiary, separators, low-stakes labels
        },
      },

      // One-shot border-pulse animations for WARNING / CRITICAL vendor cards.
      // Fires once when the dashboard is fully loaded (vendors + fleet summary
      // both settled — gated at the component layer via the `animate` prop).
      // Pattern: border holds at state color for ~300ms, then fades to the
      // resting `--rule` color over the remaining ~1200ms. A colored box-shadow
      // glow (sharp 1px ring + soft 28px halo) accompanies the peak and fades
      // with the border — that's the "more obvious" amplification.
      // `forwards` fill keeps the resting end-state with no flicker. STABLE
      // cards do NOT use these. `prefers-reduced-motion` handled at the
      // component layer.
      keyframes: {
        "card-pulse-warning": {
          "0%, 20%": {
            borderColor: "#FFAA33", // signal-amber
            boxShadow:
              "0 0 0 1px #FFAA33, 0 0 28px 4px rgba(255, 170, 51, 0.40)",
          },
          "100%": {
            borderColor: "#21263B", // --rule resting border
            boxShadow:
              "0 0 0 0 rgba(255, 170, 51, 0), 0 0 0 0 rgba(255, 170, 51, 0)",
          },
        },
        "card-pulse-critical": {
          "0%, 20%": {
            borderColor: "#FF5247", // signal-red
            boxShadow:
              "0 0 0 1px #FF5247, 0 0 28px 4px rgba(255, 82, 71, 0.42)",
          },
          "100%": {
            borderColor: "#21263B",
            boxShadow:
              "0 0 0 0 rgba(255, 82, 71, 0), 0 0 0 0 rgba(255, 82, 71, 0)",
          },
        },
      },
      animation: {
        "card-pulse-warning":
          "card-pulse-warning 1500ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "card-pulse-critical":
          "card-pulse-critical 1500ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
      },
    },
  },
  plugins: [],
};
