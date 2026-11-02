"use client";

import { FormEvent, useState } from "react";

type RecordItem = {
  title: string; abstract: string; pmid: string; doi: string;
  journal: string; year: string; source: string; url: string;
};
type SearchResult = {
  question: string; searched_at: string;
  counts: { pubmed_retrieved: number; europe_pmc_retrieved: number; unique_records: number };
  records: RecordItem[]; interpretation: string;
  source_errors: { source: string; error: string }[];
};
const API = process.env.NEXT_PUBLIC_API_URL || "https://onco-evidence-ai.onrender.com";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault(); setLoading(true); setError(""); setResult(null);
    try {
      const response = await fetch(`${API}/api/search`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question, max_results_per_source: 25})
      });
      if (!response.ok) throw new Error(`Search failed (${response.status})`);
      setResult(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to search. Check the API server.");
    } finally { setLoading(false); }
  }

  return <main className="mx-auto max-w-5xl px-5 py-12">
    <header className="mb-12">
      <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-teal-700">Clinical evidence intelligence</p>
      <h1 className="text-4xl font-bold tracking-tight">OncoEvidence AI</h1>
      <p className="mt-3 max-w-2xl text-lg text-slate-600">Search the research landscape behind a clinical question — not just one paper.</p>
    </header>
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-semibold">What clinical question are you investigating?</h2>
      <form onSubmit={submit} className="mt-5">
        <textarea value={question} onChange={e => setQuestion(e.target.value)} required minLength={5} maxLength={1000} rows={4}
          placeholder="Example: Does adaptive radiotherapy reduce xerostomia in head and neck cancer?"
          className="w-full rounded-xl border border-slate-300 p-4 outline-none focus:border-teal-700" />
        <div className="mt-4 flex items-center justify-between gap-4">
          <span className="text-xs text-slate-500">Searches PubMed and Europe PMC.</span>
          <button disabled={loading || question.trim().length < 5} className="rounded-xl bg-teal-800 px-6 py-3 font-semibold text-white disabled:opacity-50">
            {loading ? "Searching…" : "Search evidence"}
          </button>
        </div>
      </form>
      {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
    </section>
    {result && <section className="mt-8">
      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <Metric label="PubMed records" value={result.counts.pubmed_retrieved}/>
        <Metric label="Europe PMC records" value={result.counts.europe_pmc_retrieved}/>
        <Metric label="Unique records" value={result.counts.unique_records}/>
      </div>
      <div className="mb-5 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">
        <strong>Discovery only:</strong> {result.interpretation}
      </div>
      {result.source_errors.map(e => <p key={e.source} className="mb-2 text-sm text-red-700">{e.source}: {e.error}</p>)}
      <h2 className="mb-4 text-2xl font-bold">Retrieved publications</h2>
      <div className="space-y-4">{result.records.map((r, i) => <article key={`${r.pmid}-${r.doi}-${i}`} className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-teal-800">{r.source} · {r.year || "Year unavailable"}</div>
        <h3 className="font-semibold leading-snug">{r.title || "Title unavailable"}</h3>
        <p className="mt-2 text-sm text-slate-600">{r.journal}</p>
        {r.abstract && <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{r.abstract.slice(0,1100)}{r.abstract.length > 1100 ? "…" : ""}</p>}
        <div className="mt-4 flex flex-wrap gap-4 text-sm">
          {r.url && <a className="font-semibold text-teal-800 underline" href={r.url} target="_blank" rel="noreferrer">Open publication</a>}
          {r.doi && <a className="text-slate-600 underline" href={`https://doi.org/${r.doi}`} target="_blank" rel="noreferrer">DOI: {r.doi}</a>}
        </div>
      </article>)}</div>
    </section>}
    <footer className="mt-14 border-t border-slate-200 pt-5 text-xs leading-relaxed text-slate-500">
      Research-discovery prototype only. It does not provide validated clinical recommendations. Verify publications and clinical implications independently.
    </footer>
  </main>;
}
function Metric({label, value}: {label: string; value: number}) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><p className="text-sm text-slate-500">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>;
}
