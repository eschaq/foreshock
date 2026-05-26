import type { TrajectoryPoint } from "../types";

interface Props {
  points: TrajectoryPoint[];
  width?: number;
  height?: number;
}

const STATE_STROKE: Record<string, string> = {
  stable: "#3FB8AF",
  warning: "#FFAA33",
  critical: "#FF5247",
};

export function Sparkline({ points, width = 160, height = 40 }: Props) {
  if (points.length === 0) {
    return (
      <div
        className="text-ink-dim text-xs italic"
        style={{ width, height, lineHeight: `${height}px` }}
      >
        no trajectory
      </div>
    );
  }

  const min = 0;
  const max = Math.max(60, ...points.map((p) => p.score)); // anchor to 60 so
  // critical-band crossings show visually.

  const pad = 4;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;

  // Map points to SVG coords (left -> oldest, right -> latest).
  const xy = points.map((p, i) => {
    const x =
      pad +
      (points.length === 1
        ? innerW / 2
        : (i / (points.length - 1)) * innerW);
    const y = pad + innerH - ((p.score - min) / (max - min)) * innerH;
    return { x, y, state: p.state, score: p.score, date: p.date };
  });

  const path = xy.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`).join(" ");
  const last = xy[xy.length - 1];

  // Threshold guide lines at 30 and 60.
  const yFor = (v: number) =>
    pad + innerH - ((v - min) / (max - min)) * innerH;

  return (
    <svg
      width={width}
      height={height}
      role="img"
      aria-label="risk-score trajectory"
    >
      {/* threshold bands */}
      <line
        x1={pad}
        x2={width - pad}
        y1={yFor(30)}
        y2={yFor(30)}
        stroke="#FFAA33"
        strokeOpacity="0.15"
        strokeDasharray="2 2"
      />
      <line
        x1={pad}
        x2={width - pad}
        y1={yFor(60)}
        y2={yFor(60)}
        stroke="#FF5247"
        strokeOpacity="0.18"
        strokeDasharray="2 2"
      />
      {/* trajectory */}
      <path
        d={path}
        fill="none"
        stroke={STATE_STROKE[last.state] || "#9AA3B8"}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* points */}
      {xy.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={i === xy.length - 1 ? 2.5 : 1.5}
          fill={STATE_STROKE[p.state] || "#9AA3B8"}
        >
          <title>
            {p.date}: {p.score.toFixed(1)} ({p.state})
          </title>
        </circle>
      ))}
    </svg>
  );
}
