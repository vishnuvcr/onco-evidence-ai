from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.literature import search_all

router = APIRouter(tags=["literature"])


class SearchRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    max_results_per_source: int = Field(default=1000, ge=1, le=1000)


@router.post("/search")
async def search(request: SearchRequest):
    try:
        return await search_all(request.question, request.max_results_per_source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Literature source error: {exc}") from exc
