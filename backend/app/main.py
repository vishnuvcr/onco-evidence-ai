from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.search import router as search_router

app = FastAPI(
    title="OncoEvidence AI API",
    version="0.1.0",
    description="Literature discovery prototype; not for autonomous clinical decisions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}
