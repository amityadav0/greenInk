"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

function normalise(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

const WINDOW = 25;

/** True when a line of the page shares a long run of text with the quote. */
export function overlaps(line: string, quote: string): boolean {
  if (line.length < 4 || quote.length < 4) return false;
  if (quote.includes(line) || line.includes(quote)) return true;
  if (line.length < WINDOW) return false;
  for (let start = 0; start + WINDOW <= line.length; start += 8) {
    if (quote.includes(line.slice(start, start + WINDOW))) return true;
  }
  return false;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** The PDF on one page, with the cited quote highlighted in the text layer. */
export default function PdfViewer({ url, page, quote }: { url: string; page: number; quote: string }) {
  const [pages, setPages] = useState<number | null>(null);
  const [current, setCurrent] = useState(page);
  const [failed, setFailed] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const centred = useRef<number | null>(null);
  const [width, setWidth] = useState(560);
  const needle = useMemo(() => normalise(quote), [quote]);

  const measure = useCallback((node: HTMLDivElement | null) => {
    container.current = node;
    if (node) setWidth(Math.min(node.clientWidth - 2, 900));
  }, []);

  const renderText = useCallback(
    ({ str }: { str: string }) => {
      const text = normalise(str);
      const hit = current === page && overlaps(text, needle);
      return hit ? `<mark class="quote">${escapeHtml(str)}</mark>` : escapeHtml(str);
    },
    [needle, current, page],
  );

  // Scroll only the viewer's own box, once per page: scrollIntoView also scrolled the window,
  // and re-ran on every re-render (opening a fix), jumping the report back to the top.
  const centreQuote = useCallback(() => {
    const box = scroller.current;
    const mark = box?.querySelector<HTMLElement>("mark.quote");
    if (!box || !mark || centred.current === current) return;
    centred.current = current;
    const offset = mark.getBoundingClientRect().top - box.getBoundingClientRect().top;
    box.scrollTo({ top: box.scrollTop + offset - box.clientHeight / 2, behavior: "smooth" });
  }, [current]);

  if (failed) {
    return (
      <p className="p-4 text-sm text-stone-600">
        This document could not be displayed here.{" "}
        <a className="text-ink underline" href={url} target="_blank" rel="noreferrer">
          Open it directly
        </a>
        .
      </p>
    );
  }

  return (
    <div ref={measure} className="w-full">
      <div className="mb-2 flex items-center justify-between text-sm">
        <button
          className="rounded border border-stone-300 px-2 py-1 disabled:opacity-40"
          disabled={current <= 1}
          onClick={() => setCurrent((p) => p - 1)}
        >
          ‹ Prev
        </button>
        <span>
          Page {current}
          {pages ? ` of ${pages}` : ""}
          {current !== page && (
            <button className="ml-2 text-ink underline" onClick={() => setCurrent(page)}>
              back to p.{page}
            </button>
          )}
        </span>
        <button
          className="rounded border border-stone-300 px-2 py-1 disabled:opacity-40"
          disabled={pages !== null && current >= pages}
          onClick={() => setCurrent((p) => p + 1)}
        >
          Next ›
        </button>
      </div>
      <div ref={scroller} className="max-h-[calc(100vh-9rem)] overflow-y-auto rounded border border-stone-200 bg-white">
        <Document
          file={url}
          onLoadSuccess={({ numPages }) => setPages(numPages)}
          onLoadError={() => setFailed(true)}
          loading={<p className="p-6 text-sm text-stone-500">Loading the tender…</p>}
        >
          <Page
            pageNumber={current}
            width={width}
            customTextRenderer={renderText}
            onRenderTextLayerSuccess={centreQuote}
          />
        </Document>
      </div>
    </div>
  );
}
