from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Iterable

import chromadb
from chromadb.config import Settings as ChromaSettings

from langchain_text_splitters import RecursiveCharacterTextSplitter

from openai import OpenAI

from src.settings import SETTINGS


@dataclass
class DocChunk:
    id: str
    text: str
    source: str


class LocalChromaStore:
    """Chroma + OpenAI embeddings (no local torch/sentence-transformers).

    embeddings are computed on-demand and stored in chroma.
    """

    def __init__(
        self,
        persist_dir: str,
        embed_model_name: str,
        collection_name: str = "resume_chunks",
    ):
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.embed_model_name = embed_model_name
        self.openai = OpenAI(
            base_url=SETTINGS.base_url,
            api_key=SETTINGS.api_key or "",
        )

    def _embed(self, texts):
        # OpenAI embeddings API
        resp = self.openai.embeddings.create(
            model=self.embed_model_name,
            input=texts,
        )
        # resp.data is in order
        return [d.embedding for d in resp.data]

    def add_documents(self, docs: Iterable[DocChunk], batch_size: int = 64):
        ids = []
        texts = []
        metadatas = []
        for d in docs:
            ids.append(d.id)
            texts.append(d.text)
            metadatas.append({"source": d.source})

        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_texts = texts[i : i + batch_size]
            batch_metas = metadatas[i : i + batch_size]
            vecs = self._embed(batch_texts)
            self.collection.add(
                ids=batch_ids,
                documents=batch_texts,
                embeddings=vecs,
                metadatas=batch_metas,
            )

    def query(self, query_text: str, top_k: int = 8):
        qvec = self._embed([query_text])[0]
        res = self.collection.query(
            query_embeddings=[qvec],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            chunks.append(
                {
                    "text": doc,
                    "source": meta.get("source", ""),
                    "distance": dist,
                }
            )
        return chunks


def load_text_files(input_dir: str) -> list[tuple[str, str]]:
    paths = []
    for ext in ("*.txt", "*.md"):
        paths.extend(glob.glob(os.path.join(input_dir, ext)))
    items = []
    for p in paths:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            items.append((p, f.read()))
    return items


def chunk_documents(input_dir: str, chunk_size: int, chunk_overlap: int):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    raw_items = load_text_files(input_dir)
    out: list[DocChunk] = []
    for p, text in raw_items:
        parts = splitter.split_text(text)
        for idx, part in enumerate(parts):
            if part.strip():
                out.append(
                    DocChunk(
                        id=f"{os.path.basename(p)}_{idx}",
                        text=part,
                        source=p,
                    )
                )
    return out
