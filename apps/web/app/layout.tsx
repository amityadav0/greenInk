import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { CompanyProvider, CompanySwitcher } from "@/components/company";
import "./globals.css";

export const metadata: Metadata = {
  title: "Green Ink",
  description: "Find government tenders you can win, and the clauses that would get your bid rejected.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f6b3a" };

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 text-ink" aria-label="Green Ink home">
      <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden="true">
        <path
          d="M2 14c4-9 7-11 8-8s-2 9 1 9 5-11 8-10-1 9 2 9 4-6 6-7 3 2 5 1"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-lg font-semibold tracking-tight">Green Ink</span>
    </Link>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen text-stone-900 antialiased">
        <CompanyProvider>
          <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/90 backdrop-blur">
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
              <Logo />
              <CompanySwitcher />
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-4 pb-16 pt-6">{children}</main>
          <footer className="no-print mx-auto max-w-6xl px-4 pb-10 text-xs text-stone-500">
            Advisory only: Green Ink does not replace reading the tender and never submits a bid. Bids are
            public listings from GeM, linked to their official pages. Demo company is fictional.
          </footer>
        </CompanyProvider>
      </body>
    </html>
  );
}
