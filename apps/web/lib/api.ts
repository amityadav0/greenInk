// Typed client for the Green Ink API (types generated from contracts/openapi.yaml).
import type { components } from "./api/schema";

export type Schemas = components["schemas"];
export type Company = Schemas["Company"];
export type SearchResponse = Schemas["SearchResponse"];
export type BidSummary = Schemas["BidSummary"];
export type Accepted = Schemas["Accepted"];
export type AnalysisReport = Schemas["AnalysisReport"];
export type AnalysisTrace = Schemas["AnalysisTrace"];
export type Finding = Schemas["Finding"];
export type Fix = Schemas["Fix"];
export type JobEvent = Schemas["JobEvent"];
export type TenderDetail = Schemas["TenderDetail"];
export type PageText = Schemas["PageText"];
export type TriageBadge = Schemas["TriageBadge"];
export type ErrorBody = Schemas["ErrorBody"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ErrorBody,
  ) {
    super(body.message);
  }
}

async function request<T>(method: string, path: string, body?: unknown | FormData): Promise<{ status: number; data: T }> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "content-type": "application/json" };
  }
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, { code: "upstream_unavailable", message: "You appear to be offline.", retryable: true });
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error: ErrorBody =
      data && typeof data.message === "string"
        ? data
        : { code: "internal", message: "Something went wrong. Please try again.", retryable: true };
    throw new ApiError(response.status, error);
  }
  return { status: response.status, data: data as T };
}

export const api = {
  companies: () => request<Company[]>("GET", "/v1/companies").then((r) => r.data),
  createCompany: (name: string) =>
    request<Company>("POST", "/v1/companies", { name, profile: { legal_name: name } }).then((r) => r.data),
  companyFromUrl: (url: string) => request<Accepted>("POST", "/v1/companies/from-url", { url }).then((r) => r.data),
  uploadCompanyDocument: (companyId: string, file: File, kind: string) => {
    const form = new FormData();
    form.set("file", file);
    form.set("kind", kind);
    return request<Accepted>("POST", `/v1/companies/${companyId}/documents`, form).then((r) => r.data);
  },
  search: (q: string, companyId?: string) => {
    const params = new URLSearchParams({ q });
    if (companyId) params.set("company_id", companyId);
    return request<SearchResponse>("GET", `/v1/search?${params}`).then((r) => r.data);
  },
  uploadTender: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<Accepted>("POST", "/v1/tenders/upload", form).then((r) => r.data);
  },
  tender: (id: string) => request<TenderDetail>("GET", `/v1/tenders/${id}`).then((r) => r.data),
  page: (tenderId: string, pageNo: number, documentId: string) =>
    request<PageText>("GET", `/v1/tenders/${tenderId}/pages/${pageNo}?document_id=${documentId}`).then((r) => r.data),
  startAnalysis: (tenderId: string, companyId: string) =>
    request<Accepted>("POST", "/v1/analyses", { tender_id: tenderId, company_id: companyId }).then((r) => r.data),
  report: (id: string) => request<AnalysisReport>("GET", `/v1/analyses/${id}`).then((r) => r.data),
  trace: (id: string) => request<AnalysisTrace>("GET", `/v1/analyses/${id}/trace`).then((r) => r.data),
  fix: (analysisId: string, findingId: string) =>
    request<Fix | Accepted>("POST", `/v1/analyses/${analysisId}/findings/${findingId}/fix`),
};

/** Subscribe to an SSE stream; returns a function that closes it. */
export function subscribe(
  url: string,
  handlers: Record<string, (data: unknown) => void>,
  onClose?: () => void,
): () => void {
  const source = new EventSource(url, { withCredentials: true });
  for (const [event, handler] of Object.entries(handlers)) {
    source.addEventListener(event, (message) => handler(JSON.parse((message as MessageEvent).data)));
  }
  source.addEventListener("done", () => {
    source.close();
    onClose?.();
  });
  source.onerror = () => {
    // EventSource reconnects on its own (sending Last-Event-ID); give up if the server is gone.
    if (source.readyState === EventSource.CLOSED) onClose?.();
  };
  return () => source.close();
}
