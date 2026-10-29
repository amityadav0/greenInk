"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FindingsTable, FixDialog, PricePanel, Stages, TraceDrawer, VerdictCard } from "@/components/report-parts";
import {
  api,
  ApiError,
  type AnalysisReport,
  type AnalysisTrace,
  type Finding,
  type JobEvent,
  subscribe,
  type TenderDetail,
} from "@/lib/api";

const PdfViewer = dynamic(() => import("@/components/pdf-viewer"), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-stone-500">Loading viewer…</p>,
});

type Citation = { url: string; page: number; quote: string; filename: string };

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [tender, setTender] = useState<TenderDetail | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [fixing, setFixing] = useState<Finding | null>(null);
  const [trace, setTrace] = useState<AnalysisTrace | null>(null);
  const [showTrace, setShowTrace] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await api.report(id);
      setReport(next);
      setTender(await api.tender(next.analysis.tender_id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load this report.");
    }
  }, [id]);

  useEffect(() => {
    void load();
    return subscribe(
      `/v1/analyses/${id}/events`,
      {
        stage: (data) => {
          const event = data as JobEvent;
          setEvents((current) => [...current, event]);
          if (["judge", "verdict", "intel"].includes(event.stage) && event.state !== "running") void load();
        },
      },
      () => void load(),
    );
  }, [id, load]);

  async function openTrace() {
    setShowTrace(true);
    try {
      setTrace(await api.trace(id));
    } catch {
      setTrace(null);
    }
  }

  function cite(finding: Finding) {
    const documents = tender?.documents ?? [];
    const index = Math.max(0, documents.findIndex((d) => d.id === finding.requirement.document_id));
    const document = documents[index];
    if (!document) return;
    setCitation({
      url: document.download_url,
      page: finding.requirement.page_no,
      quote: finding.requirement.quote,
      // GeM attachment filenames are opaque hashes; name documents as the stages do.
      filename: index === 0 ? "Bid document" : `Attachment ${index}`,
    });
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl py-16 text-center">
        <p className="text-block">{error}</p>
        <Link href="/" className="mt-4 inline-block text-ink underline">
          Back to search
        </Link>
      </div>
    );
  }
  if (!report) return <p className="py-16 text-center text-stone-500">Loading report…</p>;

  const { analysis } = report;
  // Saved stage states first, then anything newer from the live stream.
  const stageEvents = [...report.stages.map((s) => ({ ...s, analysis_id: id, at: "" }) as JobEvent), ...events];

  return (
    <div className="grid gap-6 [overflow-wrap:anywhere] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-6">
        <div>
          <Link href="/" className="no-print text-sm text-stone-600 hover:text-ink">
            ← Search
          </Link>
          <h1 className="mt-2 text-xl font-semibold leading-snug">{report.tender.title}</h1>
          <p className="mt-1 text-sm text-stone-600">
            {report.tender.buyer ?? "Buyer not listed"} · {report.tender.source_ref}
            {report.tender.closes_at &&
              ` · closes ${new Date(report.tender.closes_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}`}
            {report.tender.official_url && (
              <>
                {" · "}
                <a href={report.tender.official_url} target="_blank" rel="noreferrer" className="text-ink underline">
                  official page
                </a>
              </>
            )}
          </p>
        </div>

        <VerdictCard analysis={analysis} findings={report.findings} onCite={cite} />

        <section className="rounded-xl border border-stone-200 bg-white p-4">
          <Stages events={stageEvents} />
        </section>

        <div className="no-print flex flex-wrap gap-2">
          <button onClick={() => void openTrace()} className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm">
            Model Trace
          </button>
          <button
            onClick={() => {
              void navigator.clipboard?.writeText(window.location.href);
              setCopied(true);
            }}
            className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm"
          >
            {copied ? "Link copied" : "Share link"}
          </button>
          <button onClick={() => window.print()} className="rounded-md border border-stone-300 bg-white px-3 py-1.5 text-sm">
            Download PDF
          </button>
        </div>

        {report.findings.length > 0 && (
          <FindingsTable analysis={analysis} findings={report.findings} onCite={cite} onFix={setFixing} />
        )}

        <section className="rounded-xl border border-stone-200 bg-white p-4">
          <h2 className="mb-2 text-lg font-semibold">Price intel</h2>
          <PricePanel intel={report.price_intel} />
        </section>
      </div>

      <aside
        className={
          citation
            ? "fixed inset-0 z-30 overflow-y-auto bg-white p-4 lg:static lg:z-auto lg:overflow-visible lg:bg-transparent lg:p-0"
            : "hidden lg:block"
        }
      >
        <div className="lg:sticky lg:top-20">
          {citation ? (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-sm text-stone-600">
                  {citation.filename} · page {citation.page}
                </p>
                <button onClick={() => setCitation(null)} className="shrink-0 text-sm text-stone-600 hover:text-stone-900">
                  Close
                </button>
              </div>
              <PdfViewer key={`${citation.url}#${citation.page}#${citation.quote}`} {...citation} />
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-stone-300 p-8 text-center text-sm text-stone-500">
              Click a page number to open the tender at that clause, with the quote highlighted.
            </div>
          )}
        </div>
      </aside>

      {fixing && <FixDialog analysisId={id} finding={fixing} onClose={() => setFixing(null)} />}
      {showTrace && <TraceDrawer trace={trace} onClose={() => setShowTrace(false)} />}
    </div>
  );
}
