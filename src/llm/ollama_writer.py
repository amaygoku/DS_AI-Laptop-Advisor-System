from __future__ import annotations

import json
import httpx

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:1b"
OLLAMA_TIMEOUT = 60.0

async def call_ollama_writer(prompt: str, payload: dict) -> str:
    """
    payload is a dict: {"query_used": {...}, "results": [...]}
    Return: Vietnamese plain text
    """
    user_content = json.dumps(payload, ensure_ascii=False)

    req = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=req)
        r.raise_for_status()
        data = r.json()

    content = (data.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama writer returned empty content.")
    return content.strip()
