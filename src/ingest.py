from __future__ import annotations

import argparse

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore, chunk_documents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_dir", default="data/personal", help="包含个人材料的目录（txt/md）")
    ap.add_argument("--persist_dir", default="data/index", help="Chroma 持久化目录")
    ap.add_argument("--collection", default="resume_chunks")
    ap.add_argument("--chunk_size", type=int, default=SETTINGS.chunk_size)
    ap.add_argument("--chunk_overlap", type=int, default=SETTINGS.chunk_overlap)
    args = ap.parse_args()

    docs = chunk_documents(
        input_dir=args.input_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    store = LocalChromaStore(
        persist_dir=args.persist_dir,
        embed_model_name=SETTINGS.embed_model,
        collection_name=args.collection,
    )

    store.add_documents(docs)
    print(f"[OK] Indexed {len(docs)} chunks into: {args.persist_dir} / collection={args.collection}")


if __name__ == "__main__":
    main()
