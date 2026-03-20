from __future__ import annotations

import hashlib
import math

# Chroma may require sqlite3 >= 3.35.0 in some environments.
# If the system sqlite is too old, pysqlite3-binary provides a newer sqlite.
try:
    import sys
    import pysqlite3  # type: ignore

    sys.modules["sqlite3"] = pysqlite3
except Exception:
    pass

import glob
import os
from dataclasses import dataclass
from typing import Iterable, List

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI

from src.settings import SETTINGS

EMBED_DIM = 384


@dataclass
class DocChunk:
    id: str
    text: str
    source: str


def _hash_to_unit_floats(seed: str, dim: int = EMBED_DIM):
    out = []
    counter = 0
    while len(out) < dim:
        h = hashlib.sha256((seed + f"::{counter}").encode("utf-8")).digest()
        for i in range(0, len(h), 4):
            if len(out) >= dim:
                break
            chunk = h[i : i + 4]
            val = int.from_bytes(chunk, "big", signed=False)
            # map to [-1, 1]
            out.append((val / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    return out


class LocalChromaStore:
    def __init__(self, persist_dir: str, embed_model_name: str, collection_name: str = "resume_chunks"):
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
        self.use_openai_embeddings = bool(SETTINGS.api_key.strip())
        self.openai = None
        if self.use_openai_embeddings:
            self.openai = OpenAI(
                base_url=SETTINGS.base_url,
                api_key=SETTINGS.api_key,
            )

    def _embed(self, texts):
        if self.use_openai_embeddings and self.openai is not None:
            resp = self.openai.embeddings.create(model=self.embed_model_name, input=texts)
            return [d.embedding for d in resp.data]
        return [_hash_to_unit_floats(t) for t in texts]

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
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            chunks.append({"text": doc, "source": meta.get("source", ""), "distance": dist})
        return chunks


def load_text_files(input_dir: str):
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
    out = []
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
