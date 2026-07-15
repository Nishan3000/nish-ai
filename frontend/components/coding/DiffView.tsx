"use client";

/** Expandable unified diff with per-line colouring. Read-only. */

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

function lineStyle(line: string): React.CSSProperties {
  if (line.startsWith("+") && !line.startsWith("+++"))
    return { color: "var(--ok)" };
  if (line.startsWith("-") && !line.startsWith("---"))
    return { color: "var(--warn)" };
  if (line.startsWith("@@")) return { color: "var(--nova)" };
  return { color: "var(--dim)" };
}

export default function DiffView({ diff }: { diff: string }) {
  const [open, setOpen] = useState(false);
  const lineCount = diff.split("\n").length;

  return (
    <div
      className="overflow-hidden rounded-xl border"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium hover:bg-[var(--surface-2)]"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        Proposed changes — unified diff ({lineCount} lines)
      </button>
      {open && (
        <pre
          className="max-h-[28rem] overflow-auto border-t px-4 py-3 font-mono text-xs leading-relaxed"
          style={{ borderColor: "var(--line)" }}
        >
          {diff.split("\n").map((line, index) => (
            <div key={index} style={lineStyle(line)}>
              {line || "\u00A0"}
            </div>
          ))}
        </pre>
      )}
    </div>
  );
}
