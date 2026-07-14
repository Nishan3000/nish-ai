"use client";

/**
 * Markdown renderer for chat messages: GitHub-flavoured markdown with
 * themed code blocks and a copy button on each block.
 */

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    // Extract the raw text from the rendered <code> child.
    const text = extractText(children);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (e.g. non-HTTPS) — silently do nothing.
    }
  };

  return (
    <div
      className="group relative overflow-hidden rounded-lg border"
      style={{ borderColor: "var(--line)", background: "var(--surface-2)" }}
    >
      <button
        onClick={copy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute right-2 top-2 flex items-center gap-1 rounded-md border px-2 py-1 text-xs opacity-0 transition-opacity focus-visible:opacity-100 group-hover:opacity-100"
        style={{
          borderColor: "var(--line)",
          background: "var(--surface)",
          color: copied ? "var(--ok)" : "var(--dim)",
        }}
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre className="overflow-x-auto p-3.5">{children}</pre>
    </div>
  );
}

function extractText(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return extractText(
      (node as { props: { children?: React.ReactNode } }).props.children,
    );
  }
  return "";
}

export default function Markdown({ content }: { content: string }) {
  return (
    <div className="prose-nova">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
