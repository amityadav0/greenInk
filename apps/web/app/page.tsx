"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { WinBadge } from "@/components/badge";
import { useCompany } from "@/components/company";
import { CompanyCard, FeaturedReports, HowItWorks } from "@/components/landing";
import { api, ApiError, type BidSummary, type SearchResponse, subscribe, type TriageBadge } from "@/lib/api";

const SUGGESTIONS = [
  "current transformer",
  "potential transformer",
  "energy meter",
  "LED street light",
  "distribution transformer",
  "LT panel",
  "cable",
  "office chair",
];

function closes(value: string | null | undefined): string {
  if (!value) return "Closing date not given";
  const date = new Date(value);
  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  const when = date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return days <= 0 ? `Closes today` : `Closes ${when} · ${days} day${days === 1 ? "" : "s"} left`;
}

export default function SearchPage() {
  const router = useRouter();
  const { company } = useCompany();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [badges, setBadges] = useState<Record<string, TriageBadge>>({});
  const [scored, setScored] = useState(false);
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUnlikely, setShowUnlikely] = useState(false);
  const closeStream = useRef<(() => void) | null>(null);

  useEffect(() => () => closeStream.current?.(), []);

  async function search(q: string) {
    if (q.trim().length < 2 || !company) return;
    setQuery(q);
    setLoading(true);
    setError(null);
    setShowUnlikely(false);
    closeStream.current?.();
    try {
      const response = await api.search(q, company.id);
      setResult(response);
      const initial: Record<string, TriageBadge> = {};
      for (const bid of response.results) if (bid.badge) initial[bid.source_ref] = bid.badge;
      setBadges(initial);
      setScored(response.results.every((bid) => bid.badge));
      closeStream.current = subscribe(
        response.events_url,
        {
          badge: (data) => {
            const event = data as { source_ref: string; badge: TriageBadge };
            setBadges((current) => ({ ...current, [event.source_ref]: event.badge }));
          },
        },
        () => setScored(true),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function open(bid: BidSummary) {
    if (!company) return;
    setOpening(bid.tender_id);
    setError(null);
    try {
      const accepted = await api.startAnalysis(bid.tender_id, company.id);
      router.push(`/report/${accepted.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not open this bid.");
      setOpening(null);
    }
  }

  async function upload(file: File) {
    if (!company) return;
    setError(null);
    setOpening("upload");
    try {
      const tender = await api.uploadTender(file);
      const accepted = await api.startAnalysis(tender.id, company.id);
      router.push(`/report/${accepted.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
      setOpening(null);
    }
  }

  const ranked = result
    ? [...result.results].sort((a, b) => rank(badges[a.source_ref], scored) - rank(badges[b.source_ref], scored))
    : [];
  // Once scoring is done, bids judged unlikely fold away: GeM's search is loose, and a wall of
  // red hides the few bids worth opening. With nothing better, the closest few stay visible.
  const likely = ranked.filter((bid) => badges[bid.source_ref]?.level !== "red");
  const folded = scored && !showUnlikely && likely.length < ranked.length;
  const visible = folded ? (likely.length > 0 ? likely : ranked.slice(0, CLOSEST_WHEN_NONE)) : ranked;
  const hidden = ranked.length - visible.length;

  return (
    <div>
      <section className="mx-auto max-w-2xl pt-6 text-center sm:pt-12">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">What do you sell?</h1>
        <p className="mt-2 text-stone-600">
          Live government tenders, ranked by whether {company?.name ?? "your company"} can win them.
        </p>
        <form
          className="mt-6 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void search(query);
          }}
        >
          <input
            autoFocus
            aria-label="Product"
            className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-4 py-3 text-base shadow-sm focus:border-ink focus:outline-none focus:ring-2 focus:ring-ink/20"
            placeholder="e.g. current transformer"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            disabled={loading || !company}
            className="rounded-lg bg-ink px-5 py-3 font-medium text-white hover:bg-ink-dark disabled:opacity-50"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => void search(s)}
              className="rounded-full border border-stone-300 bg-white px-3 py-1 text-sm text-stone-700 hover:border-ink hover:text-ink"
            >
              {s}
            </button>
          ))}
        </div>
        <label className="mt-4 inline-block cursor-pointer text-sm text-stone-600 underline-offset-2 hover:underline">
          Or upload any tender PDF (state portals, CPPP)
          <input
            type="file"
            accept="application/pdf"
            className="sr-only"
            onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
          />
        </label>
      </section>

      {error && (
        <p role="alert" className="mx-auto mt-6 max-w-2xl rounded-md bg-block-light px-4 py-3 text-sm text-block">
          {error}
        </p>
      )}

      {loading && !result && <ResultsSkeleton />}

      {!result && !loading && (
        <>
          <FeaturedReports />
          <HowItWorks />
          {company && <CompanyCard company={company} />}
        </>
      )}

      {result && (
        <section className={`mt-10 ${loading ? "opacity-50" : ""}`}>
          <p className="mb-3 text-sm text-stone-600">
            {summary(result, ranked.length - likely.length, likely.length, scored, company?.name)}
          </p>
          {result.results.length === 0 && (
            <p className="rounded-lg border border-dashed border-stone-300 p-6 text-center text-stone-600">
              No open bids match. Try a broader product name.
            </p>
          )}
          <ul className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white">
            {visible.map((bid) => (
              <li key={bid.tender_id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <WinBadge badge={badges[bid.source_ref]} pending={!scored} />
                    <span className="text-xs text-stone-500">{bid.source_ref}</span>
                  </div>
                  <p className="mt-1 font-medium leading-snug [overflow-wrap:anywhere]">{bid.title}</p>
                  <p className="mt-0.5 text-sm text-stone-600">
                    {bid.buyer ?? "Buyer not listed"}
                    {bid.quantity ? ` · Qty ${bid.quantity}` : ""} · {closes(bid.closes_at)}
                  </p>
                  {badges[bid.source_ref] && (
                    <p className="mt-0.5 text-xs text-stone-500">{badges[bid.source_ref].reason}</p>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  {bid.official_url && (
                    <a
                      href={bid.official_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-md border border-stone-300 px-3 py-2 text-sm text-stone-700 hover:bg-stone-50"
                    >
                      GeM page
                    </a>
                  )}
                  <button
                    onClick={() => void open(bid)}
                    disabled={opening !== null}
                    className="rounded-md bg-ink px-3 py-2 text-sm font-medium text-white hover:bg-ink-dark disabled:opacity-50"
                  >
                    {opening === bid.tender_id ? "Opening…" : "Check this bid"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {(hidden > 0 || showUnlikely) && (
            <button
              onClick={() => setShowUnlikely((v) => !v)}
              className="mt-3 w-full rounded-lg border border-dashed border-stone-300 px-4 py-3 text-sm text-stone-600 hover:border-ink hover:text-ink"
            >
              {showUnlikely
                ? "Hide the bids that look unlikely"
                : `Show ${hidden} more bid${hidden === 1 ? "" : "s"} that look unlikely (other products or out of reach)`}
            </button>
          )}
        </section>
      )}
    </div>
  );
}

const CLOSEST_WHEN_NONE = 5;

function summary(
  result: SearchResponse,
  unlikely: number,
  likely: number,
  scored: boolean,
  companyName: string | undefined,
): string {
  const total = result.results.length;
  if (total === 0) return `No open GeM bids for “${result.query}”.`;
  const head = `${total} ${result.cached ? "recent" : "live"} GeM bids for “${result.query}”.`;
  if (!scored) return `${head} Nemotron 3.5 Lightning is scoring each one for ${companyName ?? "your company"}…`;
  if (likely === 0)
    return `${head} None look like a good fit for ${companyName ?? "your company"}; the closest are below. Open one to see exactly why.`;
  return `${head} ${likely} worth a look for ${companyName ?? "your company"}${unlikely ? `, ${unlikely} unlikely` : ""}. Badges by Nemotron 3.5 Lightning.`;
}

function ResultsSkeleton() {
  return (
    <section className="mt-10" aria-busy="true" aria-label="Loading bids">
      <p className="mb-3 text-sm text-stone-600">Fetching live bids from GeM… this takes a few seconds.</p>
      <ul className="divide-y divide-stone-200 overflow-hidden rounded-xl border border-stone-200 bg-white">
        {[0, 1, 2, 3].map((i) => (
          <li key={i} className="animate-pulse space-y-2 p-4">
            <div className="h-4 w-20 rounded-full bg-stone-200" />
            <div className="h-4 w-3/4 rounded bg-stone-200" />
            <div className="h-3 w-1/2 rounded bg-stone-100" />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Winnable first, then stretch, then anything left unscored, then unlikely. */
function rank(badge: TriageBadge | undefined, scored: boolean): number {
  if (!badge) return scored ? 2 : 1;
  return { green: 0, amber: 1, red: 3 }[badge.level];
}
