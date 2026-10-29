"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AnalysisReport, type Company, type Finding } from "@/lib/api";
import { plainWords } from "@/lib/text";

/** Finished reports on the production deployment for the demo company; NEXT_PUBLIC_FEATURED_REPORTS
 * (comma-separated ids) overrides them elsewhere. A report that is not found simply isn't shown. */
const FEATURED_REPORTS = (process.env.NEXT_PUBLIC_FEATURED_REPORTS ?? "78465ea7-ac6d-4f00-8af5-b779570422ba")
  .split(",")
  .map((id) => id.trim())
  .filter(Boolean);

const VERDICT_LABEL = { bid: "Bid", fix_then_bid: "Fix, then bid", skip: "Skip" } as const;
const VERDICT_STYLE = {
  bid: "bg-ink-light text-ink-dark",
  fix_then_bid: "bg-amber-light text-amber",
  skip: "bg-block-light text-block",
} as const;

const STEPS = [
  ["Search", "Live GeM bids for your product, each scored for whether your company can win it."],
  ["Open a bid", "Every requirement in the tender and its attachments, with page number and the exact quote."],
  ["Decide", "Each clause checked against your papers, a verdict by rules, a drafted fix and a price band."],
];

export function HowItWorks() {
  return (
    <ol className="mx-auto mt-10 grid max-w-4xl gap-3 sm:grid-cols-3">
      {STEPS.map(([title, body], i) => (
        <li key={title} className="rounded-xl border border-stone-200 bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-ink">Step {i + 1}</p>
          <p className="mt-1 font-semibold">{title}</p>
          <p className="mt-1 text-sm text-stone-600">{body}</p>
        </li>
      ))}
    </ol>
  );
}

/** The finding a visitor should see first: the company's own papers contradicting a clause,
 * else any failed clause, else the first gap the verdict cites. */
function highlight(report: AnalysisReport): Finding | undefined {
  const fails = report.findings.filter((f) => f.status === "fail");
  const cited = new Set((report.analysis.verdict_rules ?? []).flatMap((r) => r.finding_ids ?? []));
  return (
    fails.find((f) => /trading business/i.test(f.evidence.company_has)) ??
    fails[0] ??
    report.findings.find((f) => cited.has(f.id) && f.status !== "pass")
  );
}

export function FeaturedReports() {
  const [reports, setReports] = useState<AnalysisReport[]>([]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all(FEATURED_REPORTS.map((id) => api.report(id).catch(() => null))).then((found) => {
      if (!cancelled) setReports(found.filter((r): r is AnalysisReport => r !== null && r.analysis.verdict != null));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (reports.length === 0) return null;
  return (
    <section className="mx-auto mt-10 max-w-4xl">
      <h2 className="text-lg font-semibold">See a finished report</h2>
      <p className="text-sm text-stone-600">A real GeM bid, checked for the demo company. Opens instantly.</p>
      <ul className="mt-3 space-y-3">
        {reports.map((report) => {
          const verdict = report.analysis.verdict!;
          const row = highlight(report);
          return (
            <li key={report.analysis.id}>
              <Link
                href={`/report/${report.analysis.id}`}
                className="block rounded-xl border border-stone-200 bg-white p-4 hover:border-ink"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_STYLE[verdict]}`}>
                    {VERDICT_LABEL[verdict]}
                  </span>
                  <span className="text-xs text-stone-500">
                    {report.tender.source_ref} · {report.findings.length} requirements checked
                  </span>
                </div>
                <p className="mt-1 font-medium leading-snug [overflow-wrap:anywhere]">{report.tender.title}</p>
                {row && (
                  <div
                    className={`mt-3 rounded-lg border-l-4 p-3 text-sm ${row.status === "fail" ? "border-block bg-block-light/60" : "border-amber bg-amber-light/60"}`}
                  >
                    <p className={`font-medium ${row.status === "fail" ? "text-block" : "text-amber"}`}>
                      {row.status === "fail" ? "The line that would sink this bid" : "Fix this first"} · page{" "}
                      {row.requirement.page_no}
                    </p>
                    <p className="mt-1 text-stone-800">{plainWords(row.requirement.text)}</p>
                    <p className="mt-1 text-stone-700">
                      <span className="text-stone-500">Your papers: </span>
                      {plainWords(row.reason)}
                    </p>
                  </div>
                )}
                <p className="mt-3 text-sm font-medium text-ink">Open the report, with every clause cited →</p>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function lakh(amount: number): string {
  return `₹${(amount / 100_000).toLocaleString("en-IN", { maximumFractionDigits: 1 })} lakh`;
}

/** Who the results are judged for. For the demo company, also the traps planted in its papers. */
export function CompanyCard({ company }: { company: Company }) {
  const p = company.profile;
  const turnover = p.annual_turnover ?? [];
  const latest = turnover[turnover.length - 1];
  const certs = (p.certifications ?? []).map((c) => c.name);
  return (
    <section className="mx-auto mt-10 max-w-4xl rounded-xl border border-stone-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Checking for {company.name}</h2>
        <p className="text-xs text-stone-500">
          {company.read_only ? "Fictional demo company. Add your own from the menu at the top right." : "Your company"}
        </p>
      </div>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {(p.products ?? []).length > 0 && (
          <div>
            <dt className="inline text-stone-500">Makes: </dt>
            <dd className="inline">{(p.products ?? []).join("; ")}</dd>
          </div>
        )}
        {latest && (
          <div>
            <dt className="inline text-stone-500">Turnover: </dt>
            <dd className="inline">
              {lakh(latest.amount_inr)} in {latest.fiscal_year}
              {turnover.length > 1 && ` (${turnover.length}-year average ${lakh(turnover.reduce((s, t) => s + t.amount_inr, 0) / turnover.length)})`}
            </dd>
          </div>
        )}
        <div>
          <dt className="inline text-stone-500">Certificates: </dt>
          <dd className="inline">{certs.length > 0 ? certs.join(", ") : "none on file"}</dd>
        </div>
        {p.msme?.udyam_registered && (
          <div>
            <dt className="inline text-stone-500">MSE: </dt>
            <dd className="inline capitalize">{p.msme.category ?? "registered"} enterprise (Udyam)</dd>
          </div>
        )}
      </dl>
      {company.read_only && (
        <div className="mt-3 rounded-lg bg-amber-light/60 p-3 text-sm text-stone-800">
          <p className="font-medium text-amber">Three traps are planted in its papers, as real small firms often have:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            <li>its certificate says “{p.business_nature_wording ?? "Trading Business"}”, though it manufactures;</li>
            <li>it has no BIS licence;</li>
            <li>its turnover sits just under the common ₹50 lakh threshold.</li>
          </ul>
          <p className="mt-1">Green Ink should catch each one, with the clause and page that it breaks.</p>
        </div>
      )}
    </section>
  );
}
