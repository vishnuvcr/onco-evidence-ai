"use client";

import { FormEvent, useMemo, useState } from "react";

type OutcomeItem = {
  outcome: string;
  outcome_group: string;
  endpoint?: string;
  timepoint?: string;
  population_n?: string;
  events_or_summary?: string;
  effect_measure?: string;
  effect_estimate?: string;
  confidence_interval?: string;
  p_value?: string;
  statistical_significance?: string;
  clinical_interpretation?: string;
  evidence_quotes?: { section: string; excerpt: string; location?: string }[];
};

type FullTextAppraisal = {
  status: string;
  reason?: string;
  pmcid?: string;
  appraisal?: {
    study_design_verified?: string;
    population?: string;
    intervention?: string;
    comparator?: string;
    follow_up?: string;
    outcomes?: OutcomeItem[];
    outcome_groups?: string[];
    main_findings?: string;
    methods_assessment?: string;
    limitations_reported?: string[];
    funding_and_conflicts?: string;
    risk_of_bias?: {
      tool?: string;
      overall_judgement?: string;
      note?: string;
      domains?: { domain: string; judgement: string; rationale?: string; evidence_quotes?: { section: string; excerpt: string }[] }[];
    };
    appraisal_warnings?: string[];
    framework_url?: string;
    framework_note?: string;
    license?: string;
    evidence_integrity?: { verified_excerpt_count?: number; full_text_characters_reviewed?: number };
  };
};

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
  full_text_appraisal?: FullTextAppraisal;
  exclusion_reason?: string;
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
    unique_records_before_relevance_filter?: number;
    excluded_irrelevant?: number;
  };
  source_status?: Record<string, string>;
  appraisal_summary?: {
    by_study_design?: Record<string, number>;
    by_search_relevance?: Record<string, number>;
    by_publication_year?: Record<string, number>;
  };
  records: RecordItem[];
  excluded_records?: RecordItem[];
  interpretation: string;
  source_errors: { source: string; error: string }[];
  search_strategy?: string;
  queries?: { pubmed?: string; europe_pmc?: string };
};

const API = process.env.NEXT_PUBLIC_API_URL || "https://onco-evidence-ai.onrender.com";
const PAGE_SIZE = 50;

const FILTERS = [
  { value: "all", label: "All papers" },
  { value: "benefit", label: "Outcome: benefit observed" },
  { value: "no_clear_difference", label: "Outcome: no clear difference" },
  { value: "harm", label: "Outcome: harm observed" },
  { value: "mixed", label: "Outcome: mixed findings" },
  { value: "unclear", label: "Outcome: unclear" },
  { value: "not_appraised", label: "Not yet processed" },
  { value: "full_text_unavailable", label: "Full text not accessible" },
];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [appraising, setAppraising] = useState(false);
  const [appraisalMessage, setAppraisalMessage] = useState("");
  const [appraisalError, setAppraisalError] = useState("");
  const [colabMessage, setColabMessage] = useState("");
  const [colabError, setColabError] = useState("");

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

  function exportForColab() {
    if (!result) return;
    const payload = {
      export_format: "oncoevidence-colab-v1",
      exported_at: new Date().toISOString(),
      ...result,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "oncoevidence_colab_input.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setColabMessage("Search exported. Upload this JSON into the OncoEvidence AI Colab notebook.");
  }

  async function importColabResults(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !result) return;
    setColabMessage("");
    setColabError("");
    try {
      const payload = JSON.parse(await file.text()) as { records?: RecordItem[]; inference_engine?: string };
      if (!Array.isArray(payload.records)) throw new Error("This file does not contain a records[] array.");
      const imported = new Map<string, RecordItem>();
      for (const record of payload.records) {
        [record.pmcid, record.pmid, record.doi, record.title]
          .filter(Boolean)
          .forEach((key) => imported.set(String(key).toLowerCase(), record));
      }
      let matched = 0;
      const records = result.records.map((current) => {
        const keys = [current.pmcid, current.pmid, current.doi, current.title]
          .filter(Boolean).map((key) => String(key).toLowerCase());
        const found = keys.map((key) => imported.get(key)).find(Boolean);
        if (!found?.full_text_appraisal) return current;
        matched += 1;
        return {
          ...current,
          pmcid: found.pmcid || current.pmcid,
          full_text_appraisal: found.full_text_appraisal,
        };
      });
      if (!matched) throw new Error("No records matched this search. Import the result file generated from this exact search export.");
      setResult({ ...result, records });
      setColabMessage(`Imported ${matched} Colab appraisal results into this search.`);
    } catch (err) {
      setColabError(err instanceof Error ? err.message : "Unable to import Colab results.");
    } finally {
      event.target.value = "";
    }
  }

  async function appraiseNextPaper() {
    if (!result || appraising) return;
    const workingRecords = [...result.records];
    const alreadyProcessed = workingRecords.filter((record) => !!record.full_text_appraisal).length;
    let processedThisRun = 0;
    setAppraising(true);
    setAppraisalError("");
    setAppraisalMessage("");
    try {
      while (true) {
        const index = workingRecords.findIndex((record) => !record.full_text_appraisal);
        if (index < 0) break;
        const next = workingRecords[index];
        const queuePosition = alreadyProcessed + processedThisRun + 1;
        setAppraisalMessage(`Processing paper ${queuePosition} of ${workingRecords.length}: ${next.title}`);
        const response = await fetch(`${API}/api/appraise`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ record: next }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const detail = payload.detail || `Appraisal failed (${response.status})`;
          if (response.status === 429) {
            throw new Error(`Groq free-tier quota/rate limit reached after ${processedThisRun} papers in this run. Completed results are retained. Wait for the quota window to reset, then press “Resume all results” to continue. Provider message: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
          }
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        workingRecords[index] = {
          ...next,
          pmcid: payload.pmcid || next.pmcid,
          full_text_appraisal: payload,
        };
        setResult((current) => current ? { ...current, records: [...workingRecords] } : current);
        processedThisRun += 1;
        const completed = workingRecords.filter((record) => !!record.full_text_appraisal).length;
        const appraised = workingRecords.filter((record) => record.full_text_appraisal?.status === "appraised").length;
        setAppraisalMessage(`Processed ${completed} of ${workingRecords.length} papers · ${appraised} full-text appraisals completed · ${workingRecords.length - completed} remaining.`);
        // Small spacing between successful model calls to avoid needlessly hitting free-tier RPM limits.
        if (payload.status === "appraised" && workingRecords.some((record) => !record.full_text_appraisal)) {
          await new Promise((resolve) => setTimeout(resolve, 2500));
        }
      }
      const totalProcessed = workingRecords.filter((record) => !!record.full_text_appraisal).length;
      const totalAppraised = workingRecords.filter((record) => record.full_text_appraisal?.status === "appraised").length;
      const totalRemaining = workingRecords.length - totalProcessed;
      setAppraisalMessage(
        totalRemaining === 0
          ? `Queue complete: all ${workingRecords.length} retrieved papers checked. ${totalAppraised} received full-text appraisal; ${totalProcessed - totalAppraised} were separated because reusable full text was unavailable or incomplete.`
          : `Processed ${processedThisRun} papers in this run. ${totalAppraised} appraised, ${totalProcessed - totalAppraised} separated, ${totalRemaining} remaining.`
      );
    } catch (err) {
      setAppraisalError(err instanceof Error ? err.message : "Unable to complete full-text appraisal. Completed papers remain available in this view.");
    } finally {
      setAppraising(false);
    }
  }

  const filteredRecords = useMemo(() => {
    if (!result) return [];
    if (filter === "all") return result.records;
    if (filter === "not_appraised") return result.records.filter((record) => !record.full_text_appraisal);
    if (filter === "full_text_unavailable") return result.records.filter((record) =>
      ["full_text_unavailable", "full_text_incomplete"].includes(record.full_text_appraisal?.status || "")
    );
    return result.records.filter((record) =>
      (record.full_text_appraisal?.appraisal?.outcomes || []).some((outcome) => outcome.outcome_group === filter)
    );
  }, [result, filter]);

  const visibleRecords = filteredRecords.slice(0, visibleCount);
  const processedCount = result?.records.filter((record) => !!record.full_text_appraisal).length || 0;
  const appraisedCount = result?.records.filter((record) => record.full_text_appraisal?.status === "appraised").length || 0;
  const outcomeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const record of result?.records || []) {
      for (const outcome of record.full_text_appraisal?.appraisal?.outcomes || []) {
        counts[outcome.outcome_group] = (counts[outcome.outcome_group] || 0) + 1;
      }
    }
    return counts;
  }, [result]);

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
              disabled={loading || appraising || question.trim().length < 5}
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
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Metric label="PubMed retrieved" value={result.counts.pubmed_retrieved}
              detail={result.counts.pubmed_total_matches != null ? `${result.counts.pubmed_total_matches.toLocaleString()} matching records` : undefined} />
            <Metric label="Europe PMC retrieved" value={result.counts.europe_pmc_retrieved}
              detail={result.counts.europe_pmc_total_matches != null ? `${result.counts.europe_pmc_total_matches.toLocaleString()} matching records` : undefined} />
            <Metric label="Eligible unique papers" value={result.counts.unique_records}
              detail="After deduplication and required-concept screening" />
            <Metric label="Excluded as irrelevant" value={result.counts.excluded_irrelevant || 0}
              detail={`${(result.counts.unique_records_before_relevance_filter ?? result.counts.unique_records).toLocaleString()} unique candidates screened`} />
            <Metric label="Retrieval ceiling" value={result.requested_limit_per_source || 1000} detail="Per source for this search" />
          </div>

          {(result.excluded_records?.length || 0) > 0 && (
            <details className="rounded-2xl border border-amber-200 bg-white p-5 sm:p-6">
              <summary className="cursor-pointer list-none text-base font-semibold text-slate-900">
                {result.excluded_records!.length.toLocaleString()} records excluded during relevance screening
              </summary>
              <p className="mt-2 text-sm text-slate-600">
                These records did not contain every required topic concept in their title or abstract. They are excluded from the evidence timeline, outcome segregation, and full-text appraisal queue, but retained here for transparency.
              </p>
              <div className="mt-4 max-h-96 space-y-3 overflow-y-auto">
                {result.excluded_records!.map((paper, index) => (
                  <div key={paper.pmid || paper.doi || `${paper.title}-${index}`} className="border-t border-slate-100 pt-3">
                    <p className="text-sm font-semibold text-slate-900">{paper.title || "Title unavailable"}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {[paper.year, paper.journal, paper.pmid ? `PMID: ${paper.pmid}` : ""].filter(Boolean).join(" · ")}
                    </p>
                    <p className="mt-1 text-xs text-amber-800">{paper.exclusion_reason || "Required search concepts not confirmed in title/abstract."}</p>
                    {paper.url && <a className="mt-1 inline-block text-xs font-semibold text-teal-800 underline" href={paper.url} target="_blank" rel="noreferrer">Open publication</a>}
                  </div>
                ))}
              </div>
            </details>
          )}

          <section className="rounded-2xl border border-teal-200 bg-white p-5 sm:p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-bold">Full-text appraisal engine</h2>
                <p className="mt-1 text-sm text-slate-600">
                  {appraisedCount} appraised · {processedCount - appraisedCount} separated by full-text access · {result.records.length - processedCount} remaining
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Automatically checks every eligible paper in sequence. Records missing a required search concept are excluded before appraisal; papers without reusable PMC full text are separated. If the free inference quota is reached, the queue pauses and can be resumed.
                </p>
                <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <summary className="cursor-pointer text-sm font-semibold text-slate-800">
                    Simple guide: run free appraisal in Google Colab (no coding needed)
                  </summary>
                  <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-600">
                    <li>Tap <strong>Export for free Colab</strong> below. Keep the downloaded file.</li>
                    <li>Open the <a className="font-semibold text-teal-800 underline" href="https://colab.research.google.com/github/vishnuvcr/onco-evidence-ai/blob/main/colab/OncoEvidence_AI_Free_FullText_Appraisal.ipynb" target="_blank" rel="noreferrer">OncoEvidence AI Colab notebook</a>.</li>
                    <li>Sign in to Google. If offered, choose Runtime → Change runtime type → GPU.</li>
                    <li>Press the ▶ button beside the large code cell. When asked, select the file you exported.</li>
                    <li>Allow Google Drive access. Wait for the results file to download.</li>
                    <li>Return here and tap <strong>Import Colab results</strong>. Select the downloaded results file.</li>
                  </ol>
                  <p className="mt-3 text-xs text-slate-500">If Colab stops, reopen the same notebook, run the same cell again, and upload the same search export. Completed papers are saved in Google Drive and skipped when resuming. Free GPU availability is not guaranteed.</p>
                </details>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={exportForColab}
                  className="rounded-xl border border-teal-800 px-4 py-3 text-sm font-semibold text-teal-900 hover:bg-teal-50">
                  Export for free Colab
                </button>
                <label className="cursor-pointer rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50">
                  Import Colab results
                  <input type="file" accept=".json,application/json" onChange={importColabResults} className="hidden" />
                </label>
                <button
                type="button"
                onClick={appraiseNextPaper}
                disabled={appraising || processedCount >= result.records.length}
                className="rounded-xl bg-teal-800 px-5 py-3 font-semibold text-white disabled:opacity-50"
              >
                {appraising ? "Processing all results…" : processedCount >= result.records.length ? "All papers processed" : processedCount > 0 ? "Resume all results" : "Appraise all results"}
              </button>
            </div>
            {appraisalMessage && <p className="mt-3 text-sm text-teal-800" role="status">{appraisalMessage}</p>}
            {colabMessage && <p className="mt-2 text-sm text-teal-800" role="status">{colabMessage}</p>}
            {colabError && <p className="mt-2 text-sm text-red-700" role="alert">{colabError}</p>}
            {appraisalError && <p className="mt-3 text-sm text-red-700" role="alert">{appraisalError}</p>}
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
              <OutcomeCount label="Benefit" value={outcomeCounts.benefit || 0} />
              <OutcomeCount label="No clear difference" value={outcomeCounts.no_clear_difference || 0} />
              <OutcomeCount label="Harm" value={outcomeCounts.harm || 0} />
              <OutcomeCount label="Mixed" value={outcomeCounts.mixed || 0} />
              <OutcomeCount label="Unclear" value={outcomeCounts.unclear || 0} />
            </div>
          </section>

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
              <SummaryList title="By search relevance" values={result.appraisal_summary?.by_search_relevance || {}} />
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
            <h2 className="text-xl font-bold">Publication timeline</h2>
            <p className="mt-1 text-sm text-slate-500">
              Papers are arranged by first publication year, oldest to newest. Expand a year to inspect publication details and provisional study-design classification.
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
                            {paper.study_design || "Study design unclear"} · {paper.relevance_tier || "Relevance not classified"}
                          </p>

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
                  Each outcome is grouped separately; one study can contribute to more than one finding group.
                </p>
              </div>
              <label className="text-sm">
                <span className="mb-1 block font-medium text-slate-700">Filter by full-text outcome finding</span>
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
              ({result.records.length.toLocaleString()} eligible papers after relevance screening).
            </p>
            <div className="space-y-4">
              {visibleRecords.map((record, index) => (
                <StudyCard key={record.pmid || record.doi || `${record.title}-${index}`} record={record} />
              ))}
              {filteredRecords.length === 0 && (
                <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
                  No papers match this outcome group yet. Run full-text appraisal to populate the groups.
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
        Research discovery with AI-assisted full-text extraction. Verify the extracted source passages and complete the relevant
        official risk-of-bias instrument with a human reviewer. This tool does not establish clinical recommendations or GRADE certainty.
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

function OutcomeCount({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-bold tabular-nums text-slate-900">{value}</p>
    </div>
  );
}

function FindingLabel({ value }: { value: string }) {
  const labels: Record<string, string> = {
    benefit: "Benefit observed",
    no_clear_difference: "No clear difference",
    harm: "Harm observed",
    mixed: "Mixed findings",
    unclear: "Unclear",
    not_reported: "Not reported",
  };
  const styles: Record<string, string> = {
    benefit: "bg-emerald-50 text-emerald-800",
    no_clear_difference: "bg-slate-100 text-slate-700",
    harm: "bg-rose-50 text-rose-800",
    mixed: "bg-amber-50 text-amber-900",
    unclear: "bg-slate-100 text-slate-700",
    not_reported: "bg-slate-100 text-slate-600",
  };
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${styles[value] || styles.unclear}`}>{labels[value] || value}</span>;
}

function StudyCard({ record }: { record: RecordItem }) {
  const result = record.full_text_appraisal;
  const appraisal = result?.appraisal;
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-3 flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-teal-50 px-3 py-1 text-teal-900">{record.relevance_tier || "Relevance unclassified"}</span>
        <span className="rounded-full bg-indigo-50 px-3 py-1 text-indigo-900">{appraisal?.study_design_verified || record.study_design || "Design unclear"}</span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{record.year || "Year unavailable"}</span>
        {appraisal && <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-800">Full text appraised</span>}
        {result?.status === "full_text_unavailable" && <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-900">Full text inaccessible</span>}
      </div>
      <h3 className="text-base font-semibold leading-snug text-slate-900">{record.title || "Title unavailable"}</h3>
      <p className="mt-2 text-sm text-slate-500">
        {[record.journal, record.sources?.join(" + ") || record.source].filter(Boolean).join(" · ")}
      </p>
      {record.relevance_reasons && <p className="mt-2 text-xs text-slate-500">Search relevance: {record.relevance_reasons.join(" · ")}</p>}

      {appraisal ? (
        <div className="mt-5 space-y-5">
          <section>
            <h4 className="text-sm font-bold text-slate-900">Study question and design</h4>
            <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
              <div><dt className="font-semibold text-slate-500">Population</dt><dd className="text-slate-800">{appraisal.population || "Not clearly stated in extracted text"}</dd></div>
              <div><dt className="font-semibold text-slate-500">Intervention / exposure</dt><dd className="text-slate-800">{appraisal.intervention || "Not reported"}</dd></div>
              <div><dt className="font-semibold text-slate-500">Comparator</dt><dd className="text-slate-800">{appraisal.comparator || "Not reported"}</dd></div>
              <div><dt className="font-semibold text-slate-500">Follow-up</dt><dd className="text-slate-800">{appraisal.follow_up || "Not reported"}</dd></div>
            </dl>
          </section>

          <section>
            <h4 className="text-sm font-bold text-slate-900">Outcome-by-outcome findings</h4>
            <p className="mt-1 text-xs text-slate-500">Findings are classified per endpoint, not as a single verdict for the paper.</p>
            <div className="mt-3 space-y-3">
              {(appraisal.outcomes || []).map((outcome, index) => (
                <div key={`${outcome.outcome}-${index}`} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h5 className="text-sm font-semibold text-slate-900">{outcome.outcome}</h5>
                    <FindingLabel value={outcome.outcome_group} />
                  </div>
                  <p className="mt-2 text-sm text-slate-700">{outcome.clinical_interpretation || "Interpretation not clearly stated."}</p>
                  <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      ["Endpoint", outcome.endpoint], ["Timepoint", outcome.timepoint], ["Analyzed N", outcome.population_n],
                      ["Events / summary", outcome.events_or_summary], ["Effect", [outcome.effect_measure, outcome.effect_estimate].filter(Boolean).join(": ")],
                      ["95% CI", outcome.confidence_interval], ["P value", outcome.p_value], ["Statistical significance", outcome.statistical_significance],
                    ].filter(([, value]) => !!value).map(([label, value]) => (
                      <div key={label as string} className="rounded-lg bg-slate-50 p-2">
                        <p className="font-semibold text-slate-500">{label}</p><p className="mt-1 text-slate-800">{value}</p>
                      </div>
                    ))}
                  </div>
                  {(outcome.evidence_quotes || []).map((quote, quoteIndex) => (
                    <blockquote key={quoteIndex} className="mt-3 border-l-2 border-teal-300 pl-3 text-xs leading-relaxed text-slate-600">
                      “{quote.excerpt}” <span className="font-semibold">— {quote.section}{quote.location ? `, ${quote.location}` : ""}</span>
                    </blockquote>
                  ))}
                </div>
              ))}
              {(!appraisal.outcomes || appraisal.outcomes.length === 0) && <p className="text-sm text-slate-600">No extractable outcome estimates were identified in the returned full-text sections.</p>}
            </div>
          </section>

          <section>
            <h4 className="text-sm font-bold text-slate-900">Overall interpretation</h4>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{appraisal.main_findings || "No integrated interpretation was returned."}</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{appraisal.methods_assessment}</p>
          </section>

          <section className="rounded-xl bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="text-sm font-bold text-slate-900">Risk-of-bias appraisal</h4>
              <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700">
                {appraisal.risk_of_bias?.tool || "Design-specific framework"} · {appraisal.risk_of_bias?.overall_judgement || "Not assessable"}
              </span>
            </div>
            <div className="mt-3 space-y-3">
              {(appraisal.risk_of_bias?.domains || []).map((domain, index) => (
                <div key={`${domain.domain}-${index}`} className="border-t border-slate-200 pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-800">{domain.domain}</p>
                    <span className="text-xs font-bold uppercase tracking-wide text-slate-600">{domain.judgement.replaceAll("_", " ")}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{domain.rationale}</p>
                  {(domain.evidence_quotes || []).map((quote, quoteIndex) => (
                    <blockquote key={quoteIndex} className="mt-2 border-l-2 border-slate-300 pl-3 text-xs text-slate-500">
                      “{quote.excerpt}” — {quote.section}
                    </blockquote>
                  ))}
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">{appraisal.risk_of_bias?.note}</p>
            {appraisal.framework_url && <a className="mt-2 inline-block text-sm font-semibold text-teal-800 underline" href={appraisal.framework_url} target="_blank" rel="noreferrer">Open official appraisal framework</a>}
            {appraisal.framework_note && <p className="mt-1 text-xs text-slate-500">{appraisal.framework_note}</p>}
          </section>

          {appraisal.limitations_reported && appraisal.limitations_reported.length > 0 && (
            <section>
              <h4 className="text-sm font-bold text-slate-900">Limitations acknowledged by authors</h4>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{appraisal.limitations_reported.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </section>
          )}
          <p className="text-xs text-slate-500">
            Funding / conflicts: {appraisal.funding_and_conflicts || "Not identified in extracted text"} ·
            Verified source excerpts: {appraisal.evidence_integrity?.verified_excerpt_count ?? 0}
            {appraisal.license ? ` · Licence: ${appraisal.license}` : ""}
          </p>
          {appraisal.appraisal_warnings && appraisal.appraisal_warnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
              {appraisal.appraisal_warnings.join(" · ")}
            </div>
          )}
        </div>
      ) : result?.status === "full_text_unavailable" || result?.status === "full_text_incomplete" ? (
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h4 className="text-sm font-semibold text-amber-950">Separated from full-text appraisal</h4>
          <p className="mt-1 text-sm text-amber-900">{result.reason || "Full text could not be retrieved from the open repository."}</p>
        </div>
      ) : (
        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <h4 className="text-sm font-semibold text-slate-900">Queued for full-text appraisal</h4>
          <p className="mt-1 text-sm text-slate-600">Use “Appraise next paper” above to retrieve the full text and extract its outcomes and risk-of-bias domains.</p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        {record.url && <a className="font-semibold text-teal-800 underline" href={record.url} target="_blank" rel="noreferrer">Open publication</a>}
        {record.doi && <a className="text-slate-600 underline" href={`https://doi.org/${record.doi}`} target="_blank" rel="noreferrer">DOI: {record.doi}</a>}
        {(record.pmcid || result?.pmcid) && <a className="text-slate-600 underline" href={`https://pmc.ncbi.nlm.nih.gov/articles/${result?.pmcid || record.pmcid}/`} target="_blank" rel="noreferrer">Open PMC full text</a>}
      </div>
    </article>
  );
}
