import { useLayoutEffect, useState } from "react";
import type { TrajectoryPoint } from "../types";

interface Props {
  points: TrajectoryPoint[];
  width?: number;
  height?: number;
  // When false, the draw-on animation is skipped and the line renders
  // statically. When this flips false -> true (e.g. dashboard finished
  // loading), the animation fires once. Default true so call-sites that
  // don't gate (e.g. DetailPanel) behave as before.
  animate?: boolean;
}

const STATE_STROKE: Record<string, string> = {
  stable: "#3FB8AF",
  warning: "#FFAA33",
  critical: "#FF5247",
};

// Draw-on animation for non-stable sparklines: line traces left-to-right
// in 1200ms with the DESIGN.md-spec'd ease-out-quart curve. One-shot per
// component-mount-or-gate-flip, no looping. Stable vendors render statically.
//
// Implementation: strokeDasharray = full path length, strokeDashoffset
// starts at the same value (line invisible), then transitions to 0 once
// the parent signals the dashboard is ready (the `animate` prop). Geometric
// path-length is summed from segment distances so no DOM ref or
// getTotalLength() round-trip is needed.
const DRAW_DURATION_MS = 1200;
const DRAW_EASING = "cubic-bezier(0.16, 1, 0.3, 1)";

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Sparkline({
  points,
  width = 160,
  height = 40,
  animate = true,
}: Props) {
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

  // Path total length for the draw-on dasharray trick. Pure Euclidean
  // sum of segment lengths; equivalent to SVGPathElement.getTotalLength()
  // for the M/L-only paths we generate here.
  let pathLength = 0;
  for (let i = 1; i < xy.length; i++) {
    const dx = xy[i].x - xy[i - 1].x;
    const dy = xy[i].y - xy[i - 1].y;
    pathLength += Math.sqrt(dx * dx + dy * dy);
  }

  // Only animate for warning/critical, respect prefers-reduced-motion,
  // skip the no-op single-point case (pathLength === 0), and gate on the
  // parent-supplied `animate` prop (defaults true). When animate flips
  // false -> true (dashboard finished loading), the animation fires once.
  const shouldAnimate =
    animate &&
    (last.state === "warning" || last.state === "critical") &&
    pathLength > 0 &&
    !prefersReducedMotion();

  // `drawn` controls whether the line sits at its end state (visible) or
  // is primed at the start state (invisible). Starts true (visible) when
  // we're not going to animate, so the line renders statically. When the
  // gate flips and shouldAnimate becomes true, we briefly reset to
  // invisible (transition: none), then schedule a frame to set drawn=true
  // with the 1200ms transition applied — that's the actual draw-on.
  const [drawn, setDrawn] = useState(!shouldAnimate);
  useLayoutEffect(() => {
    if (!shouldAnimate) {
      setDrawn(true); // hold the line visible if animation is gated off
      return;
    }
    setDrawn(false); // prime invisible (transition: none kicks in below)
    const id = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(id);
  }, [shouldAnimate]);

  const pathStyle: React.CSSProperties | undefined = shouldAnimate
    ? {
        strokeDasharray: `${pathLength}`,
        strokeDashoffset: drawn ? 0 : pathLength,
        // Disable the transition during the prime-invisible step so the
        // line jumps invisible without a fade; re-enable for the draw.
        transition: drawn
          ? `stroke-dashoffset ${DRAW_DURATION_MS}ms ${DRAW_EASING}`
          : "none",
      }
    : undefined;

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
        style={pathStyle}
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
