import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Deep Research Agent — Autonomous Intelligence Platform",
  description:
    "Autonomous AI deep research platform: parallel web search, evidence graph, real-time gap detection, grounded report synthesis, and claim-by-claim verification.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle cx='50' cy='50' r='46' fill='%23000000'/><circle cx='50' cy='50' r='38' fill='none' stroke='%23ffffff' stroke-width='6'/><circle cx='50' cy='50' r='18' fill='%23ffffff'/></svg>",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
