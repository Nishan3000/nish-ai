"use client";

/**
 * Memory page — full management of NISH's long-term memory.
 * List, search, filter by type, add, edit, delete (with confirmation),
 * and clear-all (with confirmation). Source and dates are read-only.
 */

import { Brain, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import ErrorBanner from "@/components/ErrorBanner";
import NishLogo from "@/components/NishLogo";
import {
  ApiError,
  clearAllMemories,
  createMemory,
  deleteMemory,
  listMemories,
  updateMemory,
} from "@/lib/api";
import {
  MEMORY_TYPE_LABELS,
  MEMORY_TYPES,
  type Memory,
  type MemoryType,
} from "@/types/memory";

function TypeBadge({ type }: { type: MemoryType }) {
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-xs"
      style={{ borderColor: "var(--line)", color: "var(--dim)" }}
    >
      {MEMORY_TYPE_LABELS[type] ?? type}
    </span>
  );
}

function MemoryEditor({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Memory;
  onSave: (data: {
    content: string;
    memory_type: MemoryType;
    importance_score: number;
  }) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [content, setContent] = useState(initial?.content ?? "");
  const [type, setType] = useState<MemoryType>(
    initial?.memory_type ?? "personal_fact",
  );
  const [importance, setImportance] = useState(
    initial?.importance_score ?? 0.5,
  );

  return (
    <div
      className="space-y-3 rounded-xl border p-4"
      style={{ borderColor: "var(--nova)", background: "var(--surface)" }}
    >
      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        placeholder="What should NISH remember? (Never include passwords, keys, or tokens — they will be rejected.)"
        rows={3}
        maxLength={2000}
        className="w-full resize-none rounded-lg border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-[var(--dim)]"
        style={{ borderColor: "var(--line)" }}
        aria-label="Memory content"
      />
      <div className="flex flex-wrap items-center gap-3">
        <label
          className="flex items-center gap-2 text-sm"
          style={{ color: "var(--dim)" }}
        >
          Type
          <select
            value={type}
            onChange={(event) => setType(event.target.value as MemoryType)}
            className="rounded-lg border px-2 py-1.5 text-sm"
            style={{ borderColor: "var(--line)", background: "var(--surface)" }}
          >
            {MEMORY_TYPES.map((memoryType) => (
              <option key={memoryType} value={memoryType}>
                {MEMORY_TYPE_LABELS[memoryType]}
              </option>
            ))}
          </select>
        </label>
        <label
          className="flex items-center gap-2 text-sm"
          style={{ color: "var(--dim)" }}
        >
          Importance
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={importance}
            onChange={(event) => setImportance(Number(event.target.value))}
            aria-label="Importance score"
          />
          <span className="w-8 font-mono text-xs">{importance.toFixed(1)}</span>
        </label>
        <div className="ml-auto flex gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border px-3 py-1.5 text-sm"
            style={{ borderColor: "var(--line)" }}
          >
            Cancel
          </button>
          <button
            onClick={() =>
              onSave({
                content,
                memory_type: type,
                importance_score: importance,
              })
            }
            disabled={content.trim().length < 3 || saving}
            className="rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-40"
            style={{ background: "var(--nova)", color: "var(--bg)" }}
          >
            {saving ? "Saving…" : "Save memory"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<MemoryType | "all">("all");

  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmingClearAll, setConfirmingClearAll] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMemories(await listMemories());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load memories.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 2500);
  };

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return memories.filter(
      (memory) =>
        (typeFilter === "all" || memory.memory_type === typeFilter) &&
        (!needle || memory.content.toLowerCase().includes(needle)),
    );
  }, [memories, query, typeFilter]);

  const handleCreate = async (data: {
    content: string;
    memory_type: MemoryType;
    importance_score: number;
  }) => {
    setSaving(true);
    setError(null);
    try {
      await createMemory(data);
      setAdding(false);
      flash("Memory saved.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (
    id: string,
    data: {
      content: string;
      memory_type: MemoryType;
      importance_score: number;
    },
  ) => {
    setSaving(true);
    setError(null);
    try {
      await updateMemory(id, data);
      setEditingId(null);
      flash("Memory updated.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setError(null);
    try {
      await deleteMemory(id);
      setDeletingId(null);
      flash("Memory deleted.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete.");
    }
  };

  const handleClearAll = async () => {
    setError(null);
    try {
      const result = await clearAllMemories();
      setConfirmingClearAll(false);
      flash(`Deleted ${result.cleared} memories.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not clear.");
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div
          className="flex min-w-48 flex-1 items-center gap-2 rounded-lg border px-3 py-2"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        >
          <Search className="h-4 w-4 shrink-0" style={{ color: "var(--dim)" }} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search memories"
            aria-label="Search memories"
            className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--dim)]"
          />
        </div>
        <select
          value={typeFilter}
          onChange={(event) =>
            setTypeFilter(event.target.value as MemoryType | "all")
          }
          aria-label="Filter by type"
          className="rounded-lg border px-2 py-2 text-sm"
          style={{ borderColor: "var(--line)", background: "var(--surface)" }}
        >
          <option value="all">All types</option>
          {MEMORY_TYPES.map((memoryType) => (
            <option key={memoryType} value={memoryType}>
              {MEMORY_TYPE_LABELS[memoryType]}
            </option>
          ))}
        </select>
        <button
          onClick={() => {
            setAdding(true);
            setEditingId(null);
          }}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium"
          style={{ background: "var(--nova)", color: "var(--bg)" }}
        >
          <Plus className="h-4 w-4" />
          Add memory
        </button>
      </div>

      {notice && (
        <p
          className="rounded-lg border px-3 py-2 text-sm"
          style={{ borderColor: "var(--ok)", color: "var(--ok)" }}
          role="status"
        >
          {notice}
        </p>
      )}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {adding && (
        <MemoryEditor
          onSave={(data) => void handleCreate(data)}
          onCancel={() => setAdding(false)}
          saving={saving}
        />
      )}

      {/* List */}
      {loading ? (
        <div
          className="flex items-center justify-center gap-2.5 py-16 text-sm"
          style={{ color: "var(--dim)" }}
        >
          <NishLogo pulsing />
          Loading memories…
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <Brain className="h-6 w-6" style={{ color: "var(--nova)" }} />
          <p className="text-sm" style={{ color: "var(--dim)" }}>
            {memories.length === 0
              ? "No long-term memories yet. Add one above, or tell NISH in chat: “Remember this: …”"
              : "No memories match your search."}
          </p>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((memory) =>
            editingId === memory.id ? (
              <li key={memory.id}>
                <MemoryEditor
                  initial={memory}
                  onSave={(data) => void handleUpdate(memory.id, data)}
                  onCancel={() => setEditingId(null)}
                  saving={saving}
                />
              </li>
            ) : (
              <li
                key={memory.id}
                className="rounded-xl border p-4"
                style={{
                  borderColor: "var(--line)",
                  background: "var(--surface)",
                }}
              >
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {memory.content}
                </p>
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  <TypeBadge type={memory.memory_type} />
                  <span className="text-xs" style={{ color: "var(--dim)" }}>
                    importance {memory.importance_score.toFixed(1)} · from{" "}
                    {memory.source === "chat_command" ? "chat" : "manual entry"}{" "}
                    ·{" "}
                    {new Date(memory.created_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                  <span className="ml-auto flex gap-1">
                    {deletingId === memory.id ? (
                      <>
                        <button
                          onClick={() => void handleDelete(memory.id)}
                          className="rounded-md px-2 py-1 text-xs font-medium"
                          style={{
                            background: "var(--warn)",
                            color: "var(--surface)",
                          }}
                        >
                          Confirm delete
                        </button>
                        <button
                          onClick={() => setDeletingId(null)}
                          aria-label="Cancel delete"
                          className="rounded-md border px-2 py-1 text-xs"
                          style={{ borderColor: "var(--line)" }}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => {
                            setEditingId(memory.id);
                            setAdding(false);
                          }}
                          aria-label="Edit memory"
                          title="Edit"
                          className="rounded-md p-1.5 hover:bg-[var(--surface-2)]"
                          style={{ color: "var(--dim)" }}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => setDeletingId(memory.id)}
                          aria-label="Delete memory"
                          title="Delete"
                          className="rounded-md p-1.5 hover:bg-[var(--surface-2)]"
                          style={{ color: "var(--warn)" }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    )}
                  </span>
                </div>
              </li>
            ),
          )}
        </ul>
      )}

      {/* Clear all */}
      {memories.length > 0 && !loading && (
        <div className="flex justify-end pt-2">
          {confirmingClearAll ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="text-xs" style={{ color: "var(--warn)" }}>
                Delete all {memories.length} memories?
              </span>
              <button
                onClick={() => void handleClearAll()}
                className="rounded-lg px-3 py-1.5 text-sm font-medium"
                style={{ background: "var(--warn)", color: "var(--surface)" }}
              >
                Yes, delete all
              </button>
              <button
                onClick={() => setConfirmingClearAll(false)}
                className="rounded-lg border px-3 py-1.5 text-sm"
                style={{ borderColor: "var(--line)" }}
              >
                Keep them
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmingClearAll(true)}
              className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm"
              style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Clear all memories
            </button>
          )}
        </div>
      )}
    </div>
  );
}
