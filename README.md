# OncoEvidence AI

Clinical literature discovery and evidence-appraisal workspace.

## Current workflow
- Search PubMed and Europe PMC, deduplicating by PMID/DOI/title.
- Resolve eligible papers to Europe PMC / PMC full text.
- Retrieve structured full-text XML only when Europe PMC identifies the article as open access and available for full-text reuse.
- Extract study design, population, intervention/comparator, follow-up, outcomes, effect estimates, confidence intervals, p-values, methods, limitations, funding and conflicts.
- Classify each outcome separately as benefit, no clear difference, harm, mixed, unclear or not reported.
- Recommend a design-specific critical-appraisal framework and produce preliminary domain-level AI-assisted judgements with source-excerpt checks.
- Separate papers whose full text is inaccessible or incomplete from those that can be appraised.

## AI inference configuration
The full-text appraisal endpoint uses the Groq OpenAI-compatible API. Configure these variables in the backend service environment (for example Render):

- `GROQ_API_KEY`: required secret from your Groq Console.
- `GROQ_MODEL`: optional; defaults to `openai/gpt-oss-120b`.

Never commit a real API key. Add it through your hosting provider's secret/environment-variable settings. Free inference accounts have model-specific quotas; the UI processes one paper per request and reports rate-limit failures.

## Architecture
- `frontend/`: Next.js + TypeScript, exported to GitHub Pages.
- `backend/`: FastAPI + Python, hosted on Render.
- Literature sources: PubMed E-utilities and Europe PMC REST API.
- Full-text source: reusable open-access PMC full text via Europe PMC fullTextXML.

## Run locally

### Backend
```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
export GROQ_API_KEY="your-key"
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Scientific integrity and limitations
This is an evidence-discovery and AI-assisted extraction tool, not an autonomous clinical decision-support system or a substitute for a completed systematic review. Full text is retrieved only where access and reuse are permitted; articles not available through the open PMC route are separated rather than treated as appraised. AI-assisted risk-of-bias judgements are preliminary and must be checked against the complete article and the official instrument by a human reviewer. The tool does not generate GRADE certainty ratings or treatment recommendations. Search coverage is limited by database indexing and query design.
