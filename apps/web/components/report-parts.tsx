"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type AnalysisTrace, type Finding, type Fix, type JobEvent, type Schemas } from "@/lib/api";
import { plainWords, readableQuote } from "@/lib/text";
import { Markdown, plainText } from "@/components/markdown";

type Verdict = NonNullable<Schemas["Analysis"]["verdict"]>;

const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  bid: { label: "Bid", className: "border-ink bg-ink-light text-ink-dark" },
  fix_then_bid: { label: "Fix, then bid", className: "border-amber bg-amber-light text-amber" },
  skip: { label: "Skip", className: "border-block bg-block-light text-block" },
};

const HEADLINE: Record<Verdict, (count: number) => string> = {
  skip: (n) => `${n === 1 ? "One requirement" : `${n} requirements`} you can't meet before this bid closes.`,
  fix_then_bid: (n) => `You can bid after closing ${n === 1 ? "one gap" : `${n} gaps`}. Each comes with a fix you can draft in one click.`,
  bid: () => "No critical or high-risk gaps found. Check the documents to prepare below.",
};

export function VerdictCard({
  analysis,
  findings,
  focus,
  onCite,
}: {
  analysis: Schemas["Analysis"];
  findings: Finding[];
  /** A finding to list first, e.g. the one a featured-report link points at. */
  focus?: string | null;
  onCite: (finding: Finding) => void;
}) {
  const { verdict, verdict_reason: reason, status } = analysis;
  if (!verdict) {
    const running = status === "queued" || status === "running";
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-5">
        <p className="text-sm font-medium uppercase tracking-wide text-stone-500">Verdict</p>
        <p className="mt-1 text-xl font-semibold">{running ? "Reading the tender…" : "No verdict"}</p>
        <p className="mt-1 text-stone-600">
          {running
            ? "Usually 30 to 60 seconds; long tenders with many attachments take up to 3 minutes. Progress is below."
            : (reason ?? "See the stage messages below.")}
        </p>
      </div>
    );
  }
  const style = VERDICT_STYLE[verdict];
  const deciding = decidingFindings(analysis, findings, focus);
  return (
    <div className={`rounded-xl border-2 p-5 ${style.className}`}>
      <p className="text-sm font-medium uppercase tracking-wide opacity-80">Verdict, computed by rules from the findings</p>
      <p className="mt-1 text-3xl font-semibold">{style.label}</p>
      <p className="mt-2 font-medium text-stone-800">{deciding.length > 0 ? HEADLINE[verdict](deciding.length) : reason}</p>
      {deciding.length > 0 && (
        <ul className="mt-3 space-y-2">
          {deciding.slice(0, TOP_BLOCKERS).map((f) => (
            <li
              key={f.id}
              className={`flex items-start gap-3 rounded-lg bg-white/70 p-3 text-sm text-stone-800 ${f.id === focus ? "ring-2 ring-current" : ""}`}
            >
              <div className="min-w-0 flex-1">
                <p className="font-medium">{plainWords(f.requirement.text)}</p>
                <p className="mt-0.5 text-stone-600">{plainWords(f.reason)}</p>
              </div>
              <button
                onClick={() => onCite(f)}
                className="shrink-0 rounded-full border border-ink/40 bg-white px-2 py-0.5 text-xs font-medium text-ink hover:bg-ink-light"
                title="Open the tender at this page"
              >
                Page {f.requirement.page_no}
              </button>
            </li>
          ))}
          {deciding.length > TOP_BLOCKERS && (
            <li className="text-sm text-stone-700">…and {deciding.length - TOP_BLOCKERS} more in Blockers below.</li>
          )}
        </ul>
      )}
    </div>
  );
}

const TOP_BLOCKERS = 3;
const SEVERITY_RANK: Record<Finding["severity"], number> = { critical: 0, high: 1, medium: 2, low: 3 };
const STATUS_RANK: Record<Finding["status"], number> = { fail: 0, missing_proof: 1, unclear: 2, pass: 3 };

function byRisk(a: Finding, b: Finding): number {
  return SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || STATUS_RANK[a.status] - STATUS_RANK[b.status];
}

/** The findings the fired verdict rule cites, most severe first; `focus` leads (and survives
 * de-duplication) when it is one of them. */
function decidingFindings(analysis: Schemas["Analysis"], findings: Finding[], focus?: string | null): Finding[] {
  const rule = (analysis.verdict_rules ?? []).find((r) => r.verdict === analysis.verdict);
  const ids = new Set(rule?.finding_ids ?? []);
  const cited = findings.filter((f) => ids.has(f.id)).sort(byRisk);
  const ordered = [...cited.filter((f) => f.id === focus), ...cited.filter((f) => f.id !== focus)];
  return dedupe(ordered).map((g) => g.finding);
}

const STAGE_LABEL: Record<string, string> = {
  ingest: "Download",
  parse: "Read pages",
  extract: "Find requirements",
  verify: "Verify citations",
  judge: "Check against company",
  verdict: "Verdict",
  intel: "Price intel",
};

export function Stages({ events }: { events: JobEvent[] }) {
  const latest = new Map<string, JobEvent>();
  for (const e of events) latest.set(e.stage, e);
  if (latest.size === 0) return <p className="text-sm text-stone-500">Queued…</p>;
  return (
    <ol className="space-y-1.5 text-sm">
      {[...latest.values()].map((e) => (
        <li key={e.stage} className="flex gap-2">
          <span aria-hidden className="w-4 shrink-0 text-center">
            {e.state === "done" || e.state === "skipped" ? "✓" : e.state === "failed" ? "✕" : "…"}
          </span>
          <span className="w-28 shrink-0 font-medium text-stone-700 sm:w-36">{STAGE_LABEL[e.stage] ?? e.stage}</span>
          <span className={`min-w-0 [overflow-wrap:anywhere] ${e.state === "failed" ? "text-block" : "text-stone-600"}`}>{e.message}</span>
        </li>
      ))}
    </ol>
  );
}

const STATUS_STYLE: Record<Finding["status"], string> = {
  fail: "bg-block-light text-block",
  missing_proof: "bg-amber-light text-amber",
  unclear: "bg-stone-100 text-stone-700",
  pass: "bg-ink-light text-ink-dark",
};
const STATUS_LABEL: Record<Finding["status"], string> = {
  fail: "You don't meet this",
  missing_proof: "Proof needed",
  unclear: "Unclear",
  pass: "You meet this",
};
const CATEGORY_LABEL: Record<string, string> = {
  turnover: "Turnover",
  experience: "Past experience",
  mse_exemption: "MSE exemption",
  startup_exemption: "Startup exemption",
  oem_authorisation: "OEM authorisation",
  bis_certification: "BIS licence",
  type_test: "Type test",
  emd: "Earnest money (EMD)",
  epbg: "Performance guarantee",
  document: "Document",
  delivery: "Delivery",
  atc: "Buyer's extra terms",
  boq_format: "Price schedule format",
  other: "Other",
};

type Group = { finding: Finding; similar: number };

/** One row per clause: the model sometimes files the same quote under two categories. */
function dedupe(findings: Finding[]): Group[] {
  const groups = new Map<string, Group>();
  for (const f of findings) {
    const key = `${f.requirement.document_id}:${f.requirement.page_no}:${f.requirement.quote.replace(/\s+/g, " ").trim().slice(0, 160).toLowerCase()}`;
    const group = groups.get(key);
    if (group) group.similar += 1;
    else groups.set(key, { finding: f, similar: 0 });
  }
  return [...groups.values()];
}

export function FindingsTable({
  analysis,
  findings,
  onCite,
  onFix,
}: {
  analysis: Schemas["Analysis"];
  findings: Finding[];
  onCite: (finding: Finding) => void;
  onFix: (finding: Finding) => void;
}) {
  const [showPass, setShowPass] = useState(false);
  const blocking = new Set((analysis.verdict_rules ?? []).flatMap((r) => r.finding_ids ?? []));
  const sorted = [...findings].sort(byRisk);
  const blockers = dedupe(sorted.filter((f) => f.status !== "pass" && blocking.has(f.id)));
  const prepare = dedupe(sorted.filter((f) => f.status !== "pass" && !blocking.has(f.id)));
  const passes = dedupe(sorted.filter((f) => f.status === "pass"));
  const row = (g: Group) => <FindingRow key={g.finding.id} group={g} onCite={onCite} onFix={onFix} />;
  return (
    <div className="space-y-6">
      <p className="text-sm text-stone-600">
        {findings.length} requirements read from the tender. Each quote below was checked against its cited page before
        it reached you.
      </p>
      <FindingGroup
        title="Blockers"
        hint="Critical or high-risk gaps. These decide the verdict."
        count={blockers.length}
        empty="No blockers."
      >
        {blockers.map(row)}
      </FindingGroup>
      <FindingGroup
        title="Documents to prepare"
        hint="Lower-risk gaps, mostly paperwork to upload with the bid."
        count={prepare.length}
        empty="Nothing else to prepare."
      >
        {prepare.map(row)}
      </FindingGroup>
      <section>
        <button
          onClick={() => setShowPass((v) => !v)}
          className="no-print flex w-full items-center justify-between rounded-xl border border-stone-200 bg-white px-4 py-3 text-left"
          aria-expanded={showPass}
        >
          <span className="text-lg font-semibold">You meet these · {passes.length}</span>
          <span className="text-sm text-stone-600">{showPass ? "Hide" : "Show"}</span>
        </button>
        {showPass && <ul className="mt-3 space-y-3">{passes.map(row)}</ul>}
      </section>
    </div>
  );
}

function FindingGroup({
  title,
  hint,
  count,
  empty,
  children,
}: {
  title: string;
  hint: string;
  count: number;
  empty: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold">
        {title} · {count}
      </h2>
      <p className="mb-2 text-sm text-stone-600">{hint}</p>
      {count === 0 ? <p className="text-sm text-stone-500">{empty}</p> : <ul className="space-y-3">{children}</ul>}
    </section>
  );
}

function FindingRow({ group, onCite, onFix }: { group: Group; onCite: (f: Finding) => void; onFix: (f: Finding) => void }) {
  const f = group.finding;
  return (
    <li className="rounded-xl border border-stone-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`rounded-full px-2 py-0.5 font-medium ${STATUS_STYLE[f.status]}`}>{STATUS_LABEL[f.status]}</span>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 capitalize text-stone-700">{f.severity}</span>
        <span className="text-stone-500">{CATEGORY_LABEL[f.requirement.category] ?? f.requirement.category}</span>
        <button
          onClick={() => onCite(f)}
          className="ml-auto rounded-full border border-ink/40 px-2 py-0.5 font-medium text-ink hover:bg-ink-light"
          title="Open the tender at this page, with the quote highlighted"
        >
          Page {f.requirement.page_no}
        </button>
      </div>
      <p className="mt-2 font-medium">{plainWords(f.requirement.text)}</p>
      <blockquote className="mt-1 whitespace-pre-line border-l-2 border-stone-300 pl-3 text-sm italic text-stone-600">
        “{readableQuote(f.requirement.quote)}”
      </blockquote>
      {f.requirement.verified && (
        <p className="mt-1 text-xs text-ink-dark" title="The quote fuzzy-matches the text of the cited page">
          ✓ Quote verified on page {f.requirement.page_no}
          {group.similar > 0 && <span className="text-stone-500"> · also listed under {group.similar} other heading{group.similar === 1 ? "" : "s"}</span>}
        </p>
      )}
      <p className="mt-2 text-sm">
        <span className="text-stone-500">You have: </span>
        {plainWords(f.evidence.company_has)}
      </p>
      {f.status !== "pass" && <p className="mt-1 text-sm text-stone-700">{plainWords(f.reason)}</p>}
      {f.status !== "pass" && (
        <button onClick={() => onFix(f)} className="no-print mt-3 rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white">
          {f.fix ? "View the fix" : "Draft the fix"}
        </button>
      )}
    </li>
  );
}

export function FixDialog({ analysisId, finding, onClose }: { analysisId: string; finding: Finding; onClose: () => void }) {
  const [fix, setFix] = useState<Fix | null>(finding.fix ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fix) return;
    let cancelled = false;
    void (async () => {
      try {
        for (let attempt = 0; attempt < 60 && !cancelled; attempt++) {
          const response = await api.fix(analysisId, finding.id);
          if (response.status === 200) {
            if (!cancelled) setFix(response.data as Fix);
            return;
          }
          await new Promise((r) => setTimeout(r, 2000));
        }
        if (!cancelled) setError("The draft is taking longer than usual. Try again in a minute.");
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not draft the fix.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // Runs once per opened finding; `fix` is only the starting value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, finding.id]);

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/30 p-4 sm:items-center" role="dialog" aria-modal="true">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
        <p className="text-xs uppercase tracking-wide text-stone-500">Fix for page {finding.requirement.page_no}</p>
        {!fix && !error && <p className="mt-2 text-stone-700">Nemotron 3 Ultra is drafting the fix…</p>}
        {error && <p className="mt-2 text-block">{error}</p>}
        {fix && (
          <>
            <h2 className="mt-1 text-xl font-semibold">{plainText(plainWords(fix.title))}</h2>
            <Markdown source={plainWords(fix.body)} className="mt-3 rounded-md bg-stone-50 p-3 text-sm leading-relaxed" />
            {(fix.steps ?? []).length > 0 && (
              <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
                {(fix.steps ?? []).map((step) => (
                  <li key={step}>{plainText(plainWords(step))}</li>
                ))}
              </ol>
            )}
            <button
              className="mt-4 rounded-md border border-stone-300 px-3 py-1.5 text-sm"
              onClick={() => void navigator.clipboard?.writeText(plainText(plainWords(fix.body)))}
            >
              Copy text
            </button>
          </>
        )}
        <div className="mt-4 text-right">
          <button onClick={onClose} className="text-sm text-stone-600 hover:text-stone-900">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function rupees(value: number | null | undefined): string {
  return value == null ? "–" : `₹${Math.round(value).toLocaleString("en-IN")}`;
}

export function PricePanel({ intel }: { intel: Schemas["PriceIntel"][] }) {
  if (intel.length === 0) return <p className="text-sm text-stone-500">Searching public prices with Tavily…</p>;
  return (
    <div className="space-y-4">
      {intel.map((p) => {
        const sources = p.sources ?? [];
        // Priced sources are what the band is computed from; the rest only show what was searched.
        const pricedSources = sources.filter((s) => s.price_inr);
        const unpriced = sources.filter((s) => !s.price_inr);
        const priced = pricedSources.length;
        return (
          <div key={p.item}>
            <p className="text-sm text-stone-600">{p.item}</p>
            {p.band_low == null ? (
              <>
                <p className="mt-1 font-semibold">No reliable unit price found</p>
                <p className="text-xs text-stone-500">
                  Tavily found {sources.length} public page{sources.length === 1 ? "" : "s"}, but fewer than two quoted a
                  unit price for this item. Check past GeM results for similar bids before quoting.
                </p>
              </>
            ) : (
              <>
                <p className="mt-1 text-2xl font-semibold">
                  {rupees(p.band_low)} – {rupees(p.band_high)}
                </p>
                <p className="text-xs text-stone-500">
                  Indicative per-unit band from {priced} public price{priced === 1 ? "" : "s"} found by Tavily (outliers
                  dropped). Not a quote: specifications vary.
                </p>
              </>
            )}
            {priced > 0 && <SourceList sources={pricedSources} />}
            {unpriced.length > 0 && (
              <details className="mt-2 text-sm">
                <summary className="cursor-pointer text-stone-500">
                  {unpriced.length} other page{unpriced.length === 1 ? "" : "s"} searched, with no unit price
                </summary>
                <SourceList sources={unpriced} />
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SourceList({ sources }: { sources: Schemas["PriceSource"][] }) {
  return (
    <ul className="mt-3 space-y-2 text-sm">
      {sources.map((s) => (
        <li key={s.url} className="flex gap-2">
          <span className={`w-20 shrink-0 text-right ${s.price_inr ? "font-medium" : "text-stone-400"}`}>
            {s.price_inr ? rupees(s.price_inr) : "–"}
          </span>
          <a className="min-w-0 truncate text-ink underline-offset-2 hover:underline" href={s.url} target="_blank" rel="noreferrer">
            {s.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

const TASK_LABEL: Record<string, string> = {
  triage: "Score bids",
  profile_url: "Profile from website",
  extract: "Find requirements",
  page_vision: "Read scanned page",
  judge: "Check against company",
  fix: "Draft a fix",
  price_intel: "Read prices",
};

export function TraceDrawer({ trace, onClose }: { trace: AnalysisTrace | null; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" role="dialog" aria-modal="true" aria-label="Model Trace">
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Model Trace</h2>
          <button onClick={onClose} className="text-sm text-stone-600">
            Close
          </button>
        </div>
        <p className="mt-1 text-sm text-stone-600">
          Every model call for this report, on Nebius Token Factory. Cached calls cost nothing.
        </p>
        {!trace && <p className="mt-4 text-sm text-stone-500">Loading…</p>}
        {trace && (
          <>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-stone-500">
                  <tr>
                    <th className="py-1 pr-2">Step</th>
                    <th className="py-1 pr-2">Model</th>
                    <th className="py-1 pr-2 text-right">Tokens</th>
                    <th className="py-1 pr-2 text-right">$</th>
                    <th className="py-1 text-right">s</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {trace.calls.map((c) => (
                    <tr key={c.id}>
                      <td className="py-1.5 pr-2">{TASK_LABEL[c.task] ?? c.task.replaceAll("_", " ")}</td>
                      <td className="py-1.5 pr-2 font-mono text-xs">
                        {c.model.replace("nvidia/", "")}
                        {c.status !== "ok" && <span className="ml-1 text-stone-500">({c.status})</span>}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {c.tokens_in.toLocaleString()} / {c.tokens_out.toLocaleString()}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{c.cost_usd.toFixed(4)}</td>
                      <td className="py-1.5 text-right tabular-nums">{(c.latency_ms / 1000).toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-sm font-medium">
              Total ${trace.totals.cost_usd.toFixed(4)} · {(trace.totals.tokens_in + trace.totals.tokens_out).toLocaleString()} tokens
            </p>
          </>
        )}
      </div>
    </div>
  );
}
