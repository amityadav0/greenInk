"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type AnalysisTrace, type Finding, type Fix, type JobEvent, type Schemas } from "@/lib/api";

type Verdict = NonNullable<Schemas["Analysis"]["verdict"]>;

const VERDICT_STYLE: Record<Verdict, { label: string; className: string }> = {
  bid: { label: "Bid", className: "border-ink bg-ink-light text-ink-dark" },
  fix_then_bid: { label: "Fix, then bid", className: "border-amber bg-amber-light text-amber" },
  skip: { label: "Skip", className: "border-block bg-block-light text-block" },
};

export function VerdictCard({ verdict, reason, status }: { verdict: Verdict | null | undefined; reason: string | null | undefined; status: string }) {
  if (!verdict) {
    const running = status === "queued" || status === "running";
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-5">
        <p className="text-sm font-medium uppercase tracking-wide text-stone-500">Verdict</p>
        <p className="mt-1 text-xl font-semibold">{running ? "Reading the tender…" : "No verdict"}</p>
        {!running && <p className="mt-1 text-stone-600">{reason ?? "See the stage messages below."}</p>}
      </div>
    );
  }
  const style = VERDICT_STYLE[verdict];
  return (
    <div className={`rounded-xl border-2 p-5 ${style.className}`}>
      <p className="text-sm font-medium uppercase tracking-wide opacity-80">Verdict, computed from the findings below</p>
      <p className="mt-1 text-3xl font-semibold">{style.label}</p>
      {reason && <p className="mt-2 text-stone-800">{reason}</p>}
    </div>
  );
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
  fail: "Fail",
  missing_proof: "Missing proof",
  unclear: "Unclear",
  pass: "Pass",
};

export function FindingsTable({
  findings,
  onCite,
  onFix,
}: {
  findings: Finding[];
  onCite: (finding: Finding) => void;
  onFix: (finding: Finding) => void;
}) {
  const [showPass, setShowPass] = useState(false);
  const risks = findings.filter((f) => f.status !== "pass");
  const shown = showPass ? findings : risks;
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          {risks.length} risk{risks.length === 1 ? "" : "s"} in {findings.length} requirements
        </h2>
        <label className="flex items-center gap-2 text-sm text-stone-600">
          <input type="checkbox" checked={showPass} onChange={(e) => setShowPass(e.target.checked)} />
          Show passing
        </label>
      </div>
      <ul className="space-y-3">
        {shown.map((f) => (
          <li key={f.id} className="rounded-xl border border-stone-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded-full px-2 py-0.5 font-medium ${STATUS_STYLE[f.status]}`}>{STATUS_LABEL[f.status]}</span>
              <span className="rounded-full bg-stone-100 px-2 py-0.5 capitalize text-stone-700">{f.severity}</span>
              <span className="text-stone-500">{f.requirement.category.replaceAll("_", " ")}</span>
              <button
                onClick={() => onCite(f)}
                className="ml-auto rounded-full border border-ink/40 px-2 py-0.5 font-medium text-ink hover:bg-ink-light"
                title="Open the tender at this page"
              >
                Page {f.requirement.page_no}
              </button>
            </div>
            <p className="mt-2 font-medium">{f.requirement.text}</p>
            <blockquote className="mt-1 border-l-2 border-stone-300 pl-3 text-sm italic text-stone-600">
              “{f.requirement.quote}”
            </blockquote>
            <p className="mt-2 text-sm">
              <span className="text-stone-500">You have: </span>
              {f.evidence.company_has}
            </p>
            {f.status !== "pass" && <p className="mt-1 text-sm text-stone-700">{f.reason}</p>}
            {f.status !== "pass" && (
              <button onClick={() => onFix(f)} className="no-print mt-3 rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white">
                {f.fix ? "View the fix" : "Draft the fix"}
              </button>
            )}
          </li>
        ))}
        {shown.length === 0 && <li className="text-sm text-stone-600">No risks found in the verified requirements.</li>}
      </ul>
    </div>
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
            <h2 className="mt-1 text-xl font-semibold">{fix.title}</h2>
            <pre className="mt-3 whitespace-pre-wrap rounded-md bg-stone-50 p-3 font-sans text-sm leading-relaxed">{fix.body}</pre>
            {(fix.steps ?? []).length > 0 && (
              <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
                {(fix.steps ?? []).map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            )}
            <button
              className="mt-4 rounded-md border border-stone-300 px-3 py-1.5 text-sm"
              onClick={() => void navigator.clipboard?.writeText(fix.body)}
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
  if (intel.length === 0) return <p className="text-sm text-stone-500">Searching past prices…</p>;
  return (
    <div className="space-y-4">
      {intel.map((p) => (
        <div key={p.item}>
          <p className="text-sm text-stone-600">{p.item}</p>
          <p className="mt-1 text-2xl font-semibold">
            {p.band_low == null ? "No unit prices found" : `${rupees(p.band_low)} – ${rupees(p.band_high)}`}
          </p>
          <p className="text-xs text-stone-500">per unit, from public sources found by Tavily</p>
          <ul className="mt-3 space-y-2 text-sm">
            {(p.sources ?? []).map((s) => (
              <li key={s.url} className="flex gap-2">
                <span className="w-20 shrink-0 text-right font-medium">{s.price_inr ? rupees(s.price_inr) : "–"}</span>
                <a className="min-w-0 truncate text-ink underline-offset-2 hover:underline" href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

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
                      <td className="py-1.5 pr-2">{c.task.replaceAll("_", " ")}</td>
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
