"use client";

/**
 * Two-column application layout. Desktop: persistent, collapsible
 * sidebar. Mobile (< md): the sidebar becomes an overlay drawer opened
 * from the header.
 */

import { useEffect, useState } from "react";

import AppSidebar from "@/components/AppSidebar";
import TopHeader from "@/components/TopHeader";

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Remember the collapse preference.
  useEffect(() => {
    setCollapsed(window.localStorage.getItem("nova.sidebar") === "collapsed");
  }, []);
  const toggleCollapse = () => {
    setCollapsed((current) => {
      window.localStorage.setItem(
        "nova.sidebar",
        current ? "expanded" : "collapsed",
      );
      return !current;
    });
  };

  // Close the drawer with Escape.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="flex h-dvh overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <AppSidebar collapsed={collapsed} onToggleCollapse={toggleCollapse} />
      </div>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            className="absolute inset-0 bg-black/40"
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 z-50">
            <AppSidebar
              collapsed={false}
              onToggleCollapse={() => setDrawerOpen(false)}
              onNavigate={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopHeader onOpenMenu={() => setDrawerOpen(true)} />
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
