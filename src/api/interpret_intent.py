from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from src.llm.sanitize import extract_json_object, normalize_intent_payload
from src.llm.intent_schema import LLMIntent
from src.llm.ollama_client import call_ollama_json_only

router = APIRouter(tags=["intent"])

PROMPT = Path("src/llm/intent_only_prompt.txt").read_text(encoding="utf-8")


class InterpretIntentRequest(BaseModel):
    user_text: str = Field(..., min_length=1)


class InterpretIntentResponse(BaseModel):
    intent: Dict[str, Any]


@router.post("/interpret_intent", response_model=InterpretIntentResponse)
async def interpret_intent(req: InterpretIntentRequest):
    # 1) Call Ollama
    try:
        llm_text = await call_ollama_json_only(PROMPT, req.user_text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama call failed: {e}")

    # 2) Strict JSON parse + schema validate
    # 2) Extract JSON + normalize + schema validate
    try:
        raw0 = extract_json_object(llm_text)
        raw1 = normalize_intent_payload(raw0)
        intent = LLMIntent.model_validate(raw1).model_dump(exclude_none=True)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Invalid/unsatisfiable LLM intent JSON: {e}",
                "raw_llm_text": llm_text,
            },
        )


    return {"intent": intent}
