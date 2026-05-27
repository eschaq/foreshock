// Compact 0-100 scoring legend for the dashboard header. The three band
// colors deliberately reference the SAME Tailwind tokens (signal-teal /
// signal-amber / signal-red) that StateBadge uses for the card states, so
// they cannot drift out of sync — change the value in tailwind.config.js
// and both the cards AND this legend update together.

const BANDS = [
  { label: "stable",   min: 0,  max: 30,  bar: "bg-signal-teal/70",  text: "text-signal-teal"  },
  { label: "warning",  min: 30, max: 60,  bar: "bg-signal-amber/70", text: "text-signal-amber" },
  { label: "critical", min: 60, max: 100, bar: "bg-signal-red/70",   text: "text-signal-red"   },
];

export function RiskScale() {
  return (
    <div className="flex items-center gap-4 text-[10px]">
      <span className="uppercase tracking-wider text-ink-dim">
        scoring bands
      </span>

      {/* The bar: three segments, widths proportional to range (30/30/40). */}
      <div className="flex items-center gap-1.5 text-ink-muted tabular-nums">
        <span>0</span>
        {BANDS.map((b) => (
          <div
            key={b.label}
            className="flex items-center gap-1.5"
            style={{ width: `${(b.max - b.min) * 1.6}px` }}
          >
            <div
              className={`flex-1 h-1.5 rounded ${b.bar}`}
              title={`${b.label}: ${b.min}-${b.max}`}
            />
            <span>{b.max}</span>
          </div>
        ))}
      </div>

      {/* Band labels — colors come from the same tokens as the StateBadges. */}
      <div className="flex items-center gap-2 uppercase tracking-wider">
        {BANDS.map((b, i) => (
          <span key={b.label} className="flex items-center gap-2">
            {i > 0 && <span className="text-ink-dim">·</span>}
            <span className={b.text}>{b.label}</span>
            <span className="text-ink-dim normal-case tracking-normal tabular-nums">
              {b.min}–{b.max}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
