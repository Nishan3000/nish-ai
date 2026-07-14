"use client";

/** Friendly empty state with four example prompt cards. */

import { Code2, FolderSearch, ListTodo, FileSearch } from "lucide-react";

import NishLogo from "@/components/NishLogo";

const EXAMPLES = [
  {
    icon: Code2,
    title: "Explain this code",
    prompt: "Explain what this code does:\n\n```python\n# paste your code here\n```",
  },
  {
    icon: FolderSearch,
    title: "Analyse my project",
    prompt:
      "I'm building a web application. Help me analyse its architecture — I'll describe the structure.",
  },
  {
    icon: ListTodo,
    title: "Create a development plan",
    prompt:
      "Create a step-by-step development plan for adding user authentication to a FastAPI application.",
  },
  {
    icon: FileSearch,
    title: "Review a file",
    prompt:
      "Review this file for bugs, readability, and best practices:\n\n```\n# paste the file here\n```",
  },
] as const;

export default function WelcomeScreen({
  onPick,
}: {
  onPick: (prompt: string) => void;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 px-4 text-center">
      <NishLogo className="h-8 w-8" />
      <div>
        <h2 className="font-display text-3xl font-medium">NISH</h2>
        <p
          className="font-display mt-1 text-sm font-medium tracking-widest uppercase"
          style={{ color: "var(--nova)" }}
        >
          Think. Learn. Build.
        </p>
        <p
          className="mx-auto mt-3 max-w-md text-sm leading-relaxed"
          style={{ color: "var(--dim)" }}
        >
          Your private assistant, running on your own machine. Ask questions,
          work through code, or plan a project — nothing leaves your computer.
        </p>
      </div>
      <div className="grid w-full max-w-xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {EXAMPLES.map(({ icon: Icon, title, prompt }) => (
          <button
            key={title}
            onClick={() => onPick(prompt)}
            className="flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left text-sm transition-colors hover:bg-[var(--surface-2)]"
            style={{ borderColor: "var(--line)", background: "var(--surface)" }}
          >
            <Icon className="h-4 w-4 shrink-0" style={{ color: "var(--nova)" }} />
            {title}
          </button>
        ))}
      </div>
    </div>
  );
}
