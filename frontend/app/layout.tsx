import type { Metadata } from "next";
import "./globals.css";

import AppShell from "@/components/AppShell";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = {
  title: "Nova AI",
  description: "A private, self-hosted AI assistant.",
};

/**
 * Applied before hydration so the stored theme/density are in effect on
 * first paint (no flash of the wrong theme). Defaults: dark, comfortable.
 */
const NO_FLASH_SCRIPT = `
(function () {
  try {
    var theme = localStorage.getItem("nova.theme") || "dark";
    if (theme === "dark") document.documentElement.classList.add("dark");
    var density = localStorage.getItem("nova.density") || "comfortable";
    document.documentElement.dataset.density = density;
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_SCRIPT }} />
        {/* Space Grotesk is loaded at runtime so builds work fully
            offline; CSS falls back to the system stack if blocked. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
