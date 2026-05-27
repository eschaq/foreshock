import { useMemo } from "react";
import type { Citation } from "../types";

// Renders text with [N] / [N,M] citation tags as anchor links to source-N
// in the source list below. The "trust contract, visible" surface.

const CITE_RX = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

interface Props {
  text: string;
  citations: Citation[];
}

export function CitedText({ text, citations }: Props) {
  const byN = useMemo(() => {
    const m = new Map<number, Citation>();
    citations.forEach((c) => m.set(c.n, c));
    return m;
  }, [citations]);

  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  let keyCounter = 0;
  let match: RegExpExecArray | null;

  CITE_RX.lastIndex = 0;
  while ((match = CITE_RX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const nums = match[1].split(",").map((s) => parseInt(s.trim(), 10));
    parts.push(
      <span key={`cite-${keyCounter++}`} className="whitespace-nowrap">
        [
        {nums.map((n, i) => {
          const cite = byN.get(n);
          const valid = cite !== undefined;
          return (
            <span key={n}>
              {i > 0 && ","}
              <a
                href={`#source-${n}`}
                title={
                  cite
                    ? `${cite.metric} · ${cite.source_url}`
                    : `unresolved citation [${n}]`
                }
                className={
                  valid
                    ? "text-signal-blue hover:underline font-medium"
                    : "text-signal-amber underline decoration-dotted"
                }
              >
                {n}
              </a>
            </span>
          );
        })}
        ]
      </span>
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return <>{parts}</>;
}
