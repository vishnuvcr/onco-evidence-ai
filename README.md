# OncoEvidence AI

Clinical literature discovery and evidence-synthesis workspace.

## MVP
- Question-first literature search
- PubMed and Europe PMC retrieval
- PMID/DOI/title deduplication
- Publication metadata and source links
- Explicit separation of discovery from screening, appraisal and synthesis

## Architecture
- `frontend/`: Next.js + TypeScript
- `backend/`: FastAPI + Python
- `docs/`: design notes

## Run locally

### Backend
```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` if the API is hosted elsewhere.

## Scientific integrity
This is a research-discovery prototype, not a validated clinical decision-support system. Search coverage is limited by database indexing and query design. Retrieved records are not automatically screened or critically appraised. Do not infer treatment recommendations from this prototype.
