from __future__ import annotations

import httpx

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:1b"
OLLAMA_TIMEOUT = 60.0

async def call_ollama_json_only(prompt: str, user_text: str) -> str:
    """
    Calls Ollama chat API and returns assistant content (expected raw JSON).
    NOTE: We keep it strict: caller must json.loads() the return.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        # Keep generation deterministic-ish
        "options": {
            "temperature": 0.0,
            "top_p": 0.9
        },
    }

    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()

    # Ollama returns: {"message": {"role":"assistant","content":"..."}, ...}
    content = (data.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned empty content.")
    return content.strip()
