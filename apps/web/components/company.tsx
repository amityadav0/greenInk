"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError, type Company } from "@/lib/api";

const STORAGE_KEY = "greenink.company";

type CompanyState = {
  companies: Company[];
  company: Company | null;
  select: (id: string) => void;
  refresh: () => Promise<void>;
  error: string | null;
};

const CompanyContext = createContext<CompanyState | null>(null);

function remembered(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function remember(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Private mode or blocked storage: the choice just won't persist.
  }
}

export function CompanyProvider({ children }: { children: React.ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCompanies(await api.companies());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load companies.");
    }
  }, []);

  useEffect(() => {
    setSelected(remembered());
    void refresh();
  }, [refresh]);

  const value = useMemo<CompanyState>(() => {
    const company = companies.find((c) => c.id === selected) ?? companies[0] ?? null;
    return {
      companies,
      company,
      error,
      refresh,
      select: (id: string) => {
        setSelected(id);
        remember(id);
      },
    };
  }, [companies, selected, error, refresh]);

  return <CompanyContext.Provider value={value}>{children}</CompanyContext.Provider>;
}

export function useCompany(): CompanyState {
  const value = useContext(CompanyContext);
  if (!value) throw new Error("useCompany outside CompanyProvider");
  return value;
}

const DOCUMENT_KINDS: [string, string][] = [
  ["udyam_certificate", "Udyam certificate"],
  ["turnover_certificate", "CA turnover certificate"],
  ["balance_sheet", "Balance sheet"],
  ["gst_certificate", "GST certificate"],
  ["bis_licence", "BIS licence"],
  ["iso_certificate", "ISO certificate"],
  ["type_test_report", "Type test report"],
  ["oem_authorisation", "OEM authorisation"],
  ["experience_certificate", "Experience / supply certificate"],
  ["other", "Other"],
];

function UploadDocument({ companyId, onUploaded }: { companyId: string; onUploaded: () => void }) {
  const [kind, setKind] = useState(DOCUMENT_KINDS[0][0]);
  const [status, setStatus] = useState<string | null>(null);

  async function upload(file: File) {
    setStatus("Uploading…");
    try {
      await api.uploadCompanyDocument(companyId, file, kind);
      setStatus("Reading the document; your profile updates in a minute.");
      onUploaded();
    } catch (e) {
      setStatus(e instanceof ApiError ? e.message : "Upload failed.");
    }
  }

  return (
    <div className="flex items-center gap-1 text-xs">
      <select
        aria-label="Document type"
        className="max-w-[8rem] rounded border border-stone-300 bg-white px-1 py-1"
        value={kind}
        onChange={(e) => setKind(e.target.value)}
      >
        {DOCUMENT_KINDS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <label className="cursor-pointer rounded border border-stone-300 bg-white px-2 py-1 hover:border-ink" title={status ?? undefined}>
        {status === "Uploading…" ? "Uploading…" : "Upload document"}
        <input
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          className="sr-only"
          onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
        />
      </label>
    </div>
  );
}

export function CompanySwitcher() {
  const { companies, company, select, refresh } = useCompany();
  const [adding, setAdding] = useState(false);

  return (
    <div className="no-print flex flex-wrap items-center justify-end gap-2">
      {company && !company.read_only && (
        <UploadDocument companyId={company.id} onUploaded={() => setTimeout(() => void refresh(), 30_000)} />
      )}
      <label className="sr-only" htmlFor="company">
        Company
      </label>
      <select
        id="company"
        className="max-w-[11rem] truncate rounded-md border border-stone-300 bg-white px-2 py-1.5 text-sm sm:max-w-xs"
        value={company?.id ?? ""}
        onChange={(e) => (e.target.value === "__add__" ? setAdding(true) : select(e.target.value))}
      >
        {companies.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.read_only ? " (demo)" : c.verified_level === "unverified" ? " (unverified)" : ""}
          </option>
        ))}
        <option value="__add__">+ Add your company…</option>
      </select>
      {adding && (
        <AddCompanyDialog
          onClose={() => setAdding(false)}
          onAdded={async (id) => {
            await refresh();
            select(id);
            setAdding(false);
          }}
        />
      )}
    </div>
  );
}

function AddCompanyDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (id: string) => Promise<void> }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setMessage(null);
    try {
      await onAdded(await action());
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/30 p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="add-company-title">
      <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-xl">
        <h2 id="add-company-title" className="text-lg font-semibold">
          Add your company
        </h2>
        <p className="mt-1 text-sm text-stone-600">
          From your website, Tavily reads your pages and Nemotron drafts a profile. It stays marked
          unverified until you upload documents.
        </p>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => (await api.companyFromUrl(url)).id);
          }}
        >
          <input
            type="url"
            required
            placeholder="https://your-company.example"
            className="min-w-0 flex-1 rounded-md border border-stone-300 px-3 py-2 text-sm"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button disabled={busy} className="rounded-md bg-ink px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
            Build
          </button>
        </form>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => (await api.createCompany(name)).id);
          }}
        >
          <input
            required
            placeholder="Or just a company name"
            className="min-w-0 flex-1 rounded-md border border-stone-300 px-3 py-2 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button disabled={busy} className="rounded-md border border-stone-300 px-3 py-2 text-sm font-medium disabled:opacity-50">
            Create
          </button>
        </form>
        {message && <p className="mt-3 text-sm text-block">{message}</p>}
        <div className="mt-5 text-right">
          <button onClick={onClose} className="text-sm text-stone-600 hover:text-stone-900">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
