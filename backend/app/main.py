from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.search import router as search_router

app = FastAPI(
    title="OncoEvidence AI API",
    version="0.2.0",
    description="Literature discovery prototype; not for autonomous clinical decisions.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://vishnuvcr.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(search_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
