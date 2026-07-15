"use client";

/** Register-project form: name + absolute path (+ description). */

import { FolderPlus } from "lucide-react";
import { useState } from "react";

export default function RegisterProject({
  onSubmit,
  busy,
}: {
  onSubmit: (data: { name: string; root_path: string; description: string }) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [description, setDescription] = useState("");
  const valid = name.trim().length > 0 && rootPath.trim().length > 2;

  return (
    <div
      className="space-y-2.5 rounded-xl border p-4"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <FolderPlus className="h-4 w-4" style={{ color: "var(--nova)" }} />
        Register a project
      </h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Project name"
          maxLength={80}
          aria-label="Project name"
          className="rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--dim)]"
          style={{ borderColor: "var(--line)" }}
        />
        <input
          value={rootPath}
          onChange={(event) => setRootPath(event.target.value)}
          placeholder="/absolute/path/to/project"
          maxLength={500}
          aria-label="Project path"
          className="rounded-lg border bg-transparent px-3 py-2 font-mono text-sm outline-none placeholder:text-[var(--dim)]"
          style={{ borderColor: "var(--line)" }}
        />
      </div>
      <input
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="Description (optional)"
        maxLength={500}
        aria-label="Project description"
        className="w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--dim)]"
        style={{ borderColor: "var(--line)" }}
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs" style={{ color: "var(--dim)" }}>
          Only registered folders can be inspected. NISH refuses its own
          installation, home directories, and filesystem roots.
        </p>
        <button
          onClick={() =>
            onSubmit({ name: name.trim(), root_path: rootPath.trim(), description })
          }
          disabled={!valid || busy}
          className="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-40"
          style={{ background: "var(--nova)", color: "var(--bg)" }}
        >
          Register
        </button>
      </div>
    </div>
  );
}
