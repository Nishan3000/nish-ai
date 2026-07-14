"use client";

/** Page header: mobile menu button, page title, connection + theme. */

import { Menu, Moon, Sun } from "lucide-react";
import { usePathname } from "next/navigation";

import ConnectionStatus from "@/components/ConnectionStatus";
import { usePreferences } from "@/components/Providers";

const TITLES: Record<string, string> = {
  "/": "Chat",
  "/agent": "Coding Agent",
  "/files": "Files",
  "/memory": "Memory",
  "/logs": "Activity Logs",
  "/about": "About NISH",
  "/settings": "Settings",
};

export function ThemeToggle() {
  const { theme, setTheme } = usePreferences();
  const isDark = theme === "dark";
  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-md p-2 hover:bg-[var(--surface-2)]"
      style={{ color: "var(--dim)" }}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export default function TopHeader({
  onOpenMenu,
}: {
  onOpenMenu: () => void;
}) {
  const pathname = usePathname();
  return (
    <header
      className="flex items-center justify-between border-b px-4 py-2"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <div className="flex items-center gap-2">
        <button
          onClick={onOpenMenu}
          aria-label="Open menu"
          className="rounded-md p-2 hover:bg-[var(--surface-2)] md:hidden"
        >
          <Menu className="h-4 w-4" />
        </button>
        <h1 className="font-display text-sm font-medium">
          {TITLES[pathname] ?? "NISH"}
        </h1>
      </div>
      <div className="flex items-center gap-1">
        <ConnectionStatus />
        <ThemeToggle />
      </div>
    </header>
  );
}
