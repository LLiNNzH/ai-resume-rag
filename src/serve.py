from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore
from src.openai_client import build_client
from src.match import build_user_prompt, MATCH_SYSTEM_PROMPT

app = FastAPI(title="AI Resume RAG")

store = LocalChromaStore(
    persist_dir="data/index",
    embed_model_name=SETTINGS.embed_model,
    collection_name="resume_chunks",
)

client = build_client()

class MatchReq(BaseModel):
    jd: str
    top_k: int | None = None

@app.post("/match")
def match(req: MatchReq):
    top_k = req.top_k or SETTINGS.top_k
    retrieved = store.query(req.jd, top_k=top_k)
    resp = client.chat.completions.create(
        model=SETTINGS.model_id,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(req.jd, retrieved)},
        ],
        temperature=0.2,
    )
    import json
    content = resp.choices[0].message.content
    data = json.loads(content)
    return data
