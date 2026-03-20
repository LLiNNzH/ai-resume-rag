from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore
from src.match import generate_result

app = FastAPI(title="AI Resume RAG")

store = LocalChromaStore(
    persist_dir="data/index",
    embed_model_name=SETTINGS.embed_model,
    collection_name="resume_chunks",
)


class MatchReq(BaseModel):
    jd: str
    top_k: int = None


@app.post("/match")
def match(req: MatchReq):
    top_k = req.top_k or SETTINGS.top_k
    retrieved = store.query(req.jd, top_k=top_k)
    return generate_result(req.jd, retrieved)
