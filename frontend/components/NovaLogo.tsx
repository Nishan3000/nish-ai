/** Nova's four-pointed star. Gold means "the model" everywhere in the UI. */
export default function NovaLogo({
  className = "h-4 w-4",
  pulsing = false,
}: {
  className?: string;
  pulsing?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`${className} ${pulsing ? "nova-pulse" : ""}`}
      style={{ color: "var(--nova)" }}
      aria-hidden="true"
    >
      <path
        d="M12 2 L14.2 9.8 L22 12 L14.2 14.2 L12 22 L9.8 14.2 L2 12 L9.8 9.8 Z"
        fill="currentColor"
      />
    </svg>
  );
}
