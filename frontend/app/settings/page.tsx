"use client";

/**
 * Settings: interface preferences (theme, density), backend connection
 * details, and clearing locally stored chats. Server-side settings
 * arrive with the accounts phase.
 */

import { Info, Monitor, Moon, Sun, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import ConnectionStatus from "@/components/ConnectionStatus";
import {
  useConnection,
  useConversations,
  usePreferences,
} from "@/components/Providers";
import { apiBaseUrl, getIdentity } from "@/lib/api";
import type { IdentityInfo } from "@/types/identity";

function SettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs" style={{ color: "var(--dim)" }}>
          {description}
        </p>
      </div>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string; icon?: typeof Sun }[];
  onChange: (next: T) => void;
}) {
  return (
    <div
      className="flex rounded-lg border p-0.5"
      style={{ borderColor: "var(--line)" }}
      role="group"
    >
      {options.map((option) => {
        const Icon = option.icon;
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            aria-pressed={isActive}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm"
            style={
              isActive
                ? { background: "var(--surface-2)", fontWeight: 500 }
                : { color: "var(--dim)" }
            }
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export default function SettingsPage() {
  const { theme, setTheme, density, setDensity } = usePreferences();
  const { health } = useConnection();
  const { conversations, clearAll } = useConversations();
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [identity, setIdentity] = useState<IdentityInfo | null>(null);

  useEffect(() => {
    getIdentity()
      .then(setIdentity)
      .catch(() => setIdentity(null)); // offline: section shows placeholders
  }, []);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-4 py-6">
      {/* Appearance */}
      <section
        className="divide-y rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <SettingRow title="Theme" description="Light or dark interface.">
          <Segmented
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: "Light", icon: Sun },
              { value: "dark", label: "Dark", icon: Moon },
            ]}
          />
        </SettingRow>
        <SettingRow
          title="Message spacing"
          description="How much room chat messages take up."
        >
          <Segmented
            value={density}
            onChange={setDensity}
            options={[
              { value: "comfortable", label: "Comfortable" },
              { value: "compact", label: "Compact" },
            ]}
          />
        </SettingRow>
      </section>

      {/* Connection */}
      <section
        className="divide-y rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <SettingRow
          title="Backend connection"
          description="Click the indicator to re-check."
        >
          <ConnectionStatus />
        </SettingRow>
        <SettingRow
          title="Model"
          description="Configured in backend/.env (OLLAMA_MODEL)."
        >
          <span className="flex items-center gap-1.5 font-mono text-sm">
            <Monitor className="h-3.5 w-3.5" style={{ color: "var(--dim)" }} />
            {health?.ollama_model ?? "unknown"}
          </span>
        </SettingRow>
        <SettingRow
          title="API address"
          description="Set with NEXT_PUBLIC_API_URL in frontend/.env.local."
        >
          <span className="font-mono text-sm">{apiBaseUrl()}</span>
        </SettingRow>
      </section>

      {/* Application identity — read-only: configured on the backend
          (identity.json); no edit UI exists because there is no secured
          update endpoint. */}
      <section
        className="divide-y rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <SettingRow
          title="Application"
          description="Identity is configured on the backend and read-only here."
        >
          <span className="flex items-center gap-1.5 text-sm font-medium">
            <Info className="h-3.5 w-3.5" style={{ color: "var(--nova)" }} />
            {identity ? `${identity.name} v${identity.version}` : "—"}
          </span>
        </SettingRow>
        <SettingRow title="Creator" description="Read-only.">
          <span className="text-sm">{identity?.creator ?? "—"}</span>
        </SettingRow>
        <SettingRow title="Lead developer" description="Read-only.">
          <span className="text-sm">{identity?.lead_developer ?? "—"}</span>
        </SettingRow>
        <SettingRow title="Project started" description="Read-only.">
          <span className="text-sm">
            {identity ? String(identity.project_started) : "—"}
          </span>
        </SettingRow>
      </section>

      {/* Data */}
      <section
        className="rounded-xl border"
        style={{ borderColor: "var(--line)", background: "var(--surface)" }}
      >
        <SettingRow
          title="Clear local chat history"
          description={`Deletes ${conversations.length} conversation${
            conversations.length === 1 ? "" : "s"
          } stored in this browser. This cannot be undone.`}
        >
          {confirmingClear ? (
            <div className="flex gap-2">
              <button
                onClick={() => {
                  clearAll();
                  setConfirmingClear(false);
                }}
                className="rounded-lg px-3 py-1.5 text-sm font-medium"
                style={{ background: "var(--warn)", color: "var(--surface)" }}
              >
                Yes, delete everything
              </button>
              <button
                onClick={() => setConfirmingClear(false)}
                className="rounded-lg border px-3 py-1.5 text-sm"
                style={{ borderColor: "var(--line)" }}
              >
                Keep chats
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmingClear(true)}
              disabled={conversations.length === 0}
              className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm disabled:opacity-40"
              style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear history
            </button>
          )}
        </SettingRow>
      </section>
    </div>
  );
}
