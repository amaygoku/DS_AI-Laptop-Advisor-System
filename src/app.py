from fastapi import FastAPI

from src.api.interpret_intent import router as intent_router
from src.api.recommend_from_text import router as recommend_from_text_router

app = FastAPI(title="Laptop Advisor API")
app.include_router(intent_router)
app.include_router(recommend_from_text_router)

@app.get("/health")
def health():
    return {"status": "ok"}
