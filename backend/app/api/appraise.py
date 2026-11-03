import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.fulltext_appraisal import appraise_full_text

router = APIRouter(tags=["full-text appraisal"])


class AppraiseRequest(BaseModel):
    record: dict[str, Any] = Field(description="One record returned by the literature search")


@router.post("/appraise")
async def appraise(request: AppraiseRequest):
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise HTTPException(
            status_code=503,
            detail="Free AI appraisal is not configured yet. Add GROQ_API_KEY to the Render service environment.",
        )
    try:
        return await appraise_full_text(request.record)
    except RuntimeError as exc:
        message = str(exc)
        if "rate limit" in message.lower():
            raise HTTPException(status_code=429, detail=message) from exc
        raise HTTPException(status_code=503, detail=message) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Full-text appraisal failed: {type(exc).__name__}: {str(exc)[:250]}") from exc
