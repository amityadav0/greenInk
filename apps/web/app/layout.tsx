import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Green Ink",
  description: "Find government tenders you can win, and the clauses that would get your bid rejected.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-neutral-900 antialiased">{children}</body>
    </html>
  );
}
