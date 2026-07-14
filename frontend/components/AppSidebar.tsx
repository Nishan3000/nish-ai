"use client";

/**
 * Left sidebar: brand, New chat, searchable conversation history,
 * navigation, collapse control, and the profile area (placeholder until
 * the accounts phase). Collapses to an icon rail on desktop; on mobile
 * AppShell renders it as an overlay drawer instead.
 */

import {
  Bot,
  Info,
  FileText,
  Brain,
  ListChecks,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Settings,
  Trash2,
  User,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import NishLogo from "@/components/NishLogo";
import { useConversations } from "@/components/Providers";

const NAV_ITEMS = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/agent", label: "Coding Agent", icon: Bot },
  { href: "/files", label: "Files", icon: FileText },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/logs", label: "Activity Logs", icon: ListChecks },
  { href: "/about", label: "About NISH", icon: Info },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export default function AppSidebar({
  collapsed,
  onToggleCollapse,
  onNavigate,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
  /** Called after any navigation — lets mobile close the drawer. */
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { conversations, activeId, select, startNew, remove } =
    useConversations();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(needle),
    );
  }, [conversations, query]);

  const openConversation = (id: string) => {
    select(id);
    router.push("/");
    onNavigate?.();
  };

  return (
    <aside
      className={`flex h-full flex-col border-r transition-[width] ${
        collapsed ? "w-14" : "w-64"
      }`}
      style={{ background: "var(--surface)", borderColor: "var(--line)" }}
      aria-label="Sidebar"
    >
      {/* Brand */}
      <div className="flex items-center gap-2 px-3 py-4">
        <NishLogo className="h-5 w-5 shrink-0" />
        {!collapsed && (
          <span className="font-display text-lg font-medium tracking-wide">
            NISH
          </span>
        )}
      </div>

      {/* New chat */}
      <div className="px-2">
        <button
          onClick={() => {
            startNew();
            router.push("/");
            onNavigate?.();
          }}
          className="flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium hover:bg-[var(--surface-2)]"
          style={{ borderColor: "var(--line)" }}
          title="New chat"
        >
          <Plus className="h-4 w-4 shrink-0" style={{ color: "var(--nova)" }} />
          {!collapsed && "New chat"}
        </button>
      </div>

      {/* Navigation */}
      <nav className="mt-4 px-2" aria-label="Main">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              title={label}
              className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${
                isActive ? "font-medium" : "hover:bg-[var(--surface-2)]"
              }`}
              style={
                isActive
                  ? { background: "var(--nova-soft)", color: "var(--text)" }
                  : { color: "var(--dim)" }
              }
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && label}
            </Link>
          );
        })}
      </nav>

      {/* Conversation history */}
      {!collapsed && (
        <div className="mt-4 flex min-h-0 flex-1 flex-col px-2">
          <div
            className="mb-1 flex items-center gap-2 rounded-lg border px-2.5 py-1.5"
            style={{ borderColor: "var(--line)" }}
          >
            <Search className="h-3.5 w-3.5" style={{ color: "var(--dim)" }} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search chats"
              aria-label="Search conversations"
              className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--dim)]"
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto py-1">
            {filtered.length === 0 && (
              <p
                className="px-3 py-2 text-xs"
                style={{ color: "var(--dim)" }}
              >
                {conversations.length === 0
                  ? "No conversations yet."
                  : "No chats match your search."}
              </p>
            )}
            {filtered.map((conversation) => (
              <div
                key={conversation.id}
                className={`group flex items-center rounded-lg ${
                  conversation.id === activeId
                    ? "bg-[var(--surface-2)]"
                    : "hover:bg-[var(--surface-2)]"
                }`}
              >
                <button
                  onClick={() => openConversation(conversation.id)}
                  className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
                  title={conversation.title}
                >
                  {conversation.title}
                </button>
                <button
                  onClick={() => remove(conversation.id)}
                  aria-label={`Delete "${conversation.title}"`}
                  className="mr-1 hidden rounded p-1 hover:bg-[var(--line)] group-hover:block"
                >
                  <Trash2
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--dim)" }}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
      {collapsed && <div className="flex-1" />}

      {/* Footer: collapse + profile */}
      <div className="border-t px-2 py-2" style={{ borderColor: "var(--line)" }}>
        <button
          onClick={onToggleCollapse}
          className="mb-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm hover:bg-[var(--surface-2)]"
          style={{ color: "var(--dim)" }}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4 shrink-0" />
          ) : (
            <PanelLeftClose className="h-4 w-4 shrink-0" />
          )}
          {!collapsed && "Collapse"}
        </button>
        <div
          className="flex items-center gap-2.5 rounded-lg px-3 py-2"
          title="Accounts arrive in a later phase"
        >
          <span
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
            style={{ background: "var(--surface-2)" }}
          >
            <User className="h-3.5 w-3.5" style={{ color: "var(--dim)" }} />
          </span>
          {!collapsed && (
            <span className="text-sm" style={{ color: "var(--dim)" }}>
              Local user
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}
