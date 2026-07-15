"use client";

/** Read-only rendering of the structured coding plan. */

import { ClipboardList } from "lucide-react";

import type { CodingPlan } from "@/types/coding";

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--dim)" }}>
        {title}
      </h4>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function PlanView({ plan }: { plan: CodingPlan }) {
  return (
    <div
      className="space-y-3 rounded-xl border p-4"
      style={{ borderColor: "var(--line)", background: "var(--surface)" }}
    >
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <ClipboardList className="h-4 w-4" style={{ color: "var(--nova)" }} />
        Implementation plan
      </h3>
      <p className="text-sm" style={{ color: "var(--dim)" }}>
        {plan.task_summary}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Section title="Steps" items={plan.steps} />
        <div className="space-y-3">
          <Section
            title="Files to modify"
            items={plan.files_to_modify.length ? plan.files_to_modify : []}
          />
          <Section title="Files to create" items={plan.files_to_create} />
          <Section title="Validation commands" items={plan.validation_commands} />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Section title="Assumptions" items={plan.assumptions} />
        <Section title="Risks" items={plan.risks} />
      </div>
      <Section title="Review before approving" items={plan.approval_requirements} />
    </div>
  );
}
