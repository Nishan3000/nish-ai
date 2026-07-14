import { FileText } from "lucide-react";

/** Placeholder until the document-upload phase (PDF/DOCX/XLSX reading). */
export default function FilesPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-4 text-center">
      <span
        className="flex h-12 w-12 items-center justify-center rounded-2xl"
        style={{ background: "var(--nova-soft)" }}
      >
        <FileText className="h-5 w-5" style={{ color: "var(--nova)" }} />
      </span>
      <h2 className="font-display text-xl font-medium">Files</h2>
      <p className="max-w-md text-sm leading-relaxed" style={{ color: "var(--dim)" }}>
        Document uploads arrive in a later phase. You&apos;ll be able to add
        PDFs, Word files, spreadsheets, and text documents, then ask NISH
        questions about them. Everything will be processed locally.
      </p>
    </div>
  );
}
