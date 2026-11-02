"use client";

import { FormEvent, useMemo, useState } from "react";

type RecordItem = {
  title: string;
  abstract: string;
  pmid: string;
  doi: string;
  pmcid?: string;
  journal: string;
  year: string;
  authors?: string[];
  publication_types?: string[];
  sources?: string[];
  source: string;
  url: string;
  relevance_tier?: string;
  relevance_reasons?: string[];
  relevance_rank?: number;
  study_design?: string;
  design_rank?: number;
  design_tier?: string;
  result_signal?: string;
  result_signal_note?: string;
  results_summary?: string;
  sample_size_detected?: number | null;
  strengths?: string[];
  limitations?: string[];
  methodology_signals?: string[];
  methodology_assessment?: string;
  appraisal_scope?: string;
  full_text_status?: string;
  recommended_appraisal_tool?: string;
  appraisal_tool_url?: string;
  appraisal_tool_note?: string;
};

type SearchResult = {
  question: string;
  searched_at: string;
  requested_limit_per_source?: number;
  counts: {
    pubmed_retrieved: number;
    pubmed_total_matches?: number;
    europe_pmc_retrieved: number;
    europe_pmc_total_matches?: number;
    unique_records: number;
  };
  source_status?: Record<string, string>;
  appraisal_summary?: {
    by_study_design?: Record<string, number>;
    by_reported_result_signal?: Record<string, number>;
    by_publication_year?: Record<string, number>;
  };
  records: RecordItem[];
  interpretation: string;
  source_errors: { source: string; error: string }[];
  search_strategy?: string;
  queries?: { pubmed?: string; europe_pmc?: string };
};

const API = process.env.NEXT_PUBLIC_API_URL || "https://onco-evidence-ai.onrender.com";
const PAGE_SIZE = 50;

const FILTERS = [
  { value: "all", label: "All papers" },
  { value: "Not assessed — full text required", label: "Awaiting full-text appraisal" },
];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    setFilter("all");
    setVisibleCount(PAGE_SIZE);
    try {
      const response = await fetch(`${API}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, max_results_per_source: 1000 }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(`Search failed (${response.status}): ${detail.slice(0, 220)}`);
      }
      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to search. Check the API server.");
    } finally {
      setLoading(false);
    }
  }

  const filteredRecords = useMemo(() => {
    if (!result) return [];
    if (filter === "all") return result.records;
    return result.records.filter((record) => (record.result_signal || "Unclear from abstract") === filter);
  }, [result, filter]);

  const visibleRecords = filteredRecords.slice(0, visibleCount);

  const timeline = useMemo(() => {
    if (!result) return [];
    const grouped = new Map<string, RecordItem[]>();
    for (const record of result.records) {
      const year = record.year && /^\d{4}$/.test(record.year) ? record.year : "Year unavailable";
      const existing = grouped.get(year) || [];
      existing.push(record);
      grouped.set(year, existing);
    }
    return Array.from(grouped.entries()).sort(([a], [b]) => {
      if (a === "Year unavailable") return 1;
      if (b === "Year unavailable") return -1;
      return Number(a) - Number(b);
    });
  }, [result]);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <header className="mb-8 sm:mb-12">
        <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-teal-700">
          Clinical evidence intelligence
        </p>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">OncoEvidence AI</h1>
        <p className="mt-3 max-w-3xl text-base text-slate-600 sm:text-lg">
          Search the research landscape behind a clinical question, compare what studies report,
          and follow the evidence across publication years.
        </p>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <h2 className="text-xl font-semibold">What clinical question are you investigating?</h2>
        <form onSubmit={submit} className="mt-5">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            required
            minLength={5}
            maxLength={1000}
            rows={4}
            placeholder="Example: Does adaptive radiotherapy reduce xerostomia in head and neck cancer?"
            className="w-full rounded-xl border border-slate-300 p-4 outline-none focus:border-teal-700"
          />
          <div className="mt-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <span className="text-xs text-slate-500">PubMed + Europe PMC · Up to 1,000 records per source</span>
            <button
              disabled={loading || question.trim().length < 5}
              className="rounded-xl bg-teal-800 px-6 py-3 font-semibold text-white disabled:opacity-50"
            >
              {loading ? "Searching up to 1,000 per source…" : "Search evidence"}
            </button>
          </div>
        </form>
        {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
      </section>

      {loading && (
        <p className="mt-5 text-sm text-slate-600" role="status">
          Searching both databases and organizing the returned records. Large searches may take longer.
        </p>
      )}

      {result && (
        <section className="mt-8 space-y-8">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="PubMed retrieved" value={result.counts.pubmed_retrieved}
              detail={result.counts.pubmed_total_matches != null ? `${result.counts.pubmed_total_matches.toLocaleString()} matching records` : undefined} />
            <Metric label="Europe PMC retrieved" value={result.counts.europe_pmc_retrieved}
              detail={result.counts.europe_pmc_total_matches != null ? `${result.counts.europe_pmc_total_matches.toLocaleString()} matching records` : undefined} />
            <Metric label="Unique papers" value={result.counts.unique_records} detail="After PMID / DOI / title deduplication" />
            <Metric label="Retrieval ceiling" value={result.requested_limit_per_source || 1000} detail="Per source for this search" />
          </div>

          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950">
            <strong>Important appraisal boundary:</strong> {result.interpretation}
          </div>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-bold">Database status</h2>
                <p className="mt-1 text-sm text-slate-500">A source reporting an error is not counted as having zero matching literature.</p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold">
                <StatusPill label="PubMed" status={result.source_status?.PubMed || "unknown"} />
                <StatusPill label="Europe PMC" status={result.source_status?.["Europe PMC"] || "unknown"} />
              </div>
            </div>
            {result.source_status?.["Europe PMC route"] && (
              <p className="mt-3 text-xs text-slate-500">Europe PMC request route: {result.source_status["Europe PMC route"]}</p>
            )}
            {result.source_errors.map((item) => (
              <p key={item.source} className="mt-3 text-sm text-red-700">
                {item.source}: {item.error}
              </p>
            ))}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <h2 className="text-xl font-bold">Evidence landscape</h2>
            <p className="mt-1 text-sm text-slate-500">Automated grouping of the retrieved abstracts, not a formal certainty-of-evidence grade.</p>
            <div className="mt-5 grid gap-6 lg:grid-cols-2">
              <SummaryList title="By study design" values={result.appraisal_summary?.by_study_design || {}} />
              <SummaryList title="By reported result signal" values={result.appraisal_summary?.by_reported_result_signal || {}} />
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <h2 className="text-xl font-bold">Results timeline</h2>
            <p className="mt-1 text-sm text-slate-500">
              Papers are arranged by first publication year, oldest to newest. Expand a year to inspect its findings.
            </p>
            {timeline.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">No timeline can be built because no records were retrieved.</p>
            ) : (
              <div className="mt-5 space-y-3">
                {timeline.map(([year, papers]) => (
                  <details key={year} className="group rounded-xl border border-slate-200 p-4">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-semibold">
                      <span>{year}</span>
                      <span className="text-sm font-normal text-slate-500">{papers.length} paper(s)</span>
                    </summary>
                    <div className="mt-4 space-y-3 border-l-2 border-teal-200 pl-4">
                      {papers.map((paper, index) => (
                        <div key={paper.pmid || paper.doi || `${paper.title}-${index}`}>
                          <p className="text-sm font-semibold">{paper.title || "Title unavailable"}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {paper.study_design || "Study design unclear"} · {paper.result_signal || "Result signal unclear"}
                          </p>
                          {paper.results_summary && (
                            <p className="mt-1 text-sm leading-relaxed text-slate-600">{paper.results_summary}</p>
                          )}
                          {paper.url && <a className="mt-1 inline-block text-xs font-semibold text-teal-800 underline" href={paper.url} target="_blank" rel="noreferrer">Open paper</a>}
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-2xl font-bold">Study-by-study appraisal</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Sorted by study-design signal, then reported result signal, then publication year.
                </p>
              </div>
              <label className="text-sm">
                <span className="mb-1 block font-medium text-slate-700">Filter by reported result</span>
                <select
                  value={filter}
                  onChange={(e) => { setFilter(e.target.value); setVisibleCount(PAGE_SIZE); }}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 sm:min-w-64"
                >
                  {FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
            <p className="mb-4 text-sm text-slate-600">
              Showing {visibleRecords.length.toLocaleString()} of {filteredRecords.length.toLocaleString()} papers in this view
              ({result.records.length.toLocaleString()} retrieved in total).
            </p>
            <div className="space-y-4">
              {visibleRecords.map((record, index) => (
                <StudyCard key={record.pmid || record.doi || `${record.title}-${index}`} record={record} />
              ))}
              {filteredRecords.length === 0 && (
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
                  No papers match this result-signal filter.
                </div>
              )}
            </div>
            {visibleCount < filteredRecords.length && (
              <button
                onClick={() => setVisibleCount((count) => Math.min(count + PAGE_SIZE, filteredRecords.length))}
                className="mt-5 w-full rounded-xl border border-teal-800 px-5 py-3 font-semibold text-teal-900 hover:bg-teal-50"
              >
                Show next {Math.min(PAGE_SIZE, filteredRecords.length - visibleCount)} papers
              </button>
            )}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <h2 className="text-lg font-bold">Search strategy used</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{result.search_strategy}</p>
            {result.queries?.pubmed && (
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold text-teal-800">View database queries</summary>
                <p className="mt-3 text-xs font-semibold text-slate-700">PubMed</p>
                <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{result.queries.pubmed}</pre>
                <p className="mt-3 text-xs font-semibold text-slate-700">Europe PMC</p>
                <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{result.queries.europe_pmc}</pre>
              </details>
            )}
          </section>
        </section>
      )}

      <footer className="mt-14 border-t border-slate-200 pt-5 text-xs leading-relaxed text-slate-500">
        Research discovery and preliminary abstract screening only. This tool does not establish clinical recommendations,
        formal risk of bias, or certainty of evidence. Verify each paper and its full text before clinical or academic use.
      </footer>
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: number; detail?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value.toLocaleString()}</p>
      {detail && <p className="mt-1 text-xs text-slate-400">{detail}</p>}
    </div>
  );
}

function StatusPill({ label, status }: { label: string; status: string }) {
  const okay = status === "ok";
  return (
    <span className={`rounded-full px-3 py-1 ${okay ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>
      {label}: {status}
    </span>
  );
}

function SummaryList({ title, values }: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-800">{title}</h3>
      {entries.length === 0 ? <p className="text-sm text-slate-500">No data.</p> : (
        <div className="space-y-3">
          {entries.map(([label, value]) => {
            const total = entries.reduce((sum, entry) => sum + entry[1], 0) || 1;
            const width = Math.max(2, Math.round((value / total) * 100));
            return (
              <div key={label}>
                <div className="mb-1 flex justify-between gap-3 text-xs">
                  <span className="text-slate-600">{label}</span>
                  <span className="font-semibold tabular-nums text-slate-800">{value}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-teal-700" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StudyCard({ record }: { record: RecordItem }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-3 flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-teal-50 px-3 py-1 text-teal-900">{record.relevance_tier || "Relevance unclassified"}</span>
        <span className="rounded-full bg-indigo-50 px-3 py-1 text-indigo-900">{record.study_design || "Design unclear"} · provisional</span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{record.year || "Year unavailable"}</span>
        <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-900">Outcome not appraised</span>
      </div>
      <h3 className="text-base font-semibold leading-snug text-slate-900">{record.title || "Title unavailable"}</h3>
      <p className="mt-2 text-sm text-slate-500">
        {[record.journal, record.sources?.join(" + ") || record.source].filter(Boolean).join(" · ")}
      </p>
      {record.relevance_reasons && (
        <p className="mt-2 text-xs text-slate-500">Relevance rationale: {record.relevance_reasons.join(" · ")}</p>
      )}

      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <h4 className="text-sm font-semibold text-amber-950">Full-text appraisal pending</h4>
        <p className="mt-1 text-sm leading-relaxed text-amber-950">
          This record is currently being shown for literature discovery and relevance screening.
          We have not yet verified its outcome estimates, strengths, limitations, or risk of bias
          from the complete article. No favorable or unfavorable conclusion is assigned.
        </p>
        {record.full_text_status && (
          <p className="mt-2 text-xs leading-relaxed text-amber-900">{record.full_text_status}</p>
        )}
      </div>

      <div className="mt-4 rounded-xl bg-slate-50 p-4">
        <h4 className="text-sm font-semibold text-slate-800">Provisional appraisal framework</h4>
        <p className="mt-1 text-sm font-semibold text-slate-800">
          {record.recommended_appraisal_tool || "Manual design confirmation required"}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-slate-600">
          {record.appraisal_tool_note || "Confirm the study design from the complete Methods section before using an appraisal tool."}
        </p>
        {record.appraisal_tool_url && (
          <a className="mt-2 inline-block text-sm font-semibold text-teal-800 underline" href={record.appraisal_tool_url} target="_blank" rel="noreferrer">
            Open official appraisal resource
          </a>
        )}
        <p className="mt-2 text-xs text-slate-500">
          This is a tool recommendation only. No risk-of-bias questionnaire has been completed or scored.
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        {record.url && <a className="font-semibold text-teal-800 underline" href={record.url} target="_blank" rel="noreferrer">Open publication</a>}
        {record.doi && <a className="text-slate-600 underline" href={`https://doi.org/${record.doi}`} target="_blank" rel="noreferrer">DOI: {record.doi}</a>}
        {record.pmcid && <a className="text-slate-600 underline" href={`https://pmc.ncbi.nlm.nih.gov/articles/${record.pmcid}/`} target="_blank" rel="noreferrer">Open PMC full text (check licence)</a>}
      </div>
    </article>
  );
}
