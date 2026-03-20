from __future__ import annotations

import argparse
import json
from typing import Any

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore
from src.openai_client import build_client


MATCH_SYSTEM_PROMPT = """你是一个求职简历助手。
目标：根据给定 JD（岗位描述）与已检索到的个人材料片段，生成适合投递的“简历定制内容（Markdown）”。

要求：
1) 必须基于检索证据生成，不能凭空编造。
2) 每个匹配要点（matched_points）都必须包含 evidence_snippet（从检索片段原文抽取/复述，尽量贴近原句）。
3) 如果证据不足，必须放到 questions_to_clarify 里，而不是编。
4) 输出必须是 JSON（不要包含多余文字），结构固定如下：
{
  "matched_points": [
    {"point": "...", "evidence_snippet": "...", "why_matched": "..."}
  ],
  "gaps": [
    {"gap": "...", "suggestion": "..."}
  ],
  "tailored_sections": {
    "summary": "...",
    "skills": "...",
    "experience_projects": "..."
  },
  "questions_to_clarify": ["..."]
}
"""


def build_user_prompt(jd: str, retrieved_chunks: list[dict[str, Any]]):
    joined = []
    for i, c in enumerate(retrieved_chunks, 1):
        joined.append(
            f"[材料片段{i}] (source={c.get('source','')})\n{c.get('text','')}"
        )
    context = "\n\n".join(joined)
    return f"JD如下：\n{jd}\n\n---\n已检索到的个人材料片段如下：\n{context}\n\n请生成定制简历内容。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jd_file", required=True, help="JD 文本文件路径")
    ap.add_argument("--persist_dir", default="data/index", help="Chroma 持久化目录")
    ap.add_argument("--top_k", type=int, default=SETTINGS.top_k)
    ap.add_argument("--out_md", default="output_match.md")
    ap.add_argument("--collection", default="resume_chunks")
    args = ap.parse_args()
    
    with open(args.jd_file, "r", encoding="utf-8", errors="ignore") as f:
        jd = f.read().strip()

    store = LocalChromaStore(
        persist_dir=args.persist_dir,
        embed_model_name=SETTINGS.embed_model,
        collection_name=args.collection,
    )

    retrieved = store.query(jd, top_k=args.top_k)

    client = build_client()

    resp = client.chat.completions.create(
        model=SETTINGS.model_id,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(jd, retrieved)},
        ],
        temperature=0.2,
    )

    content = resp.choices[0].message.content
    data = json.loads(content)

    # 渲染 Markdown
    md = []
    md.append("# 匹配要点（带证据）")
    for x in data.get("matched_points", []):
        md.append(f"- **要点**：{x.get('point','')}\n  - **证据**：{x.get('evidence_snippet','')}\n  - **匹配原因**：{x.get('why_matched','')}")

    md.append("\n# 缺口与补强建议")
    for x in data.get("gaps", []):
        md.append(f"- **缺口**：{x.get('gap','')}\n  - **建议**：{x.get('suggestion','')}")

    md.append("\n# 可直接粘贴到简历的定制段落（Markdown）")
    tailored = data.get("tailored_sections", {})
    md.append("## Summary")
    md.append(tailored.get("summary", ""))
    md.append("\n## Skills")
    md.append(tailored.get("skills", ""))
    md.append("\n## Experience/Projects")
    md.append(tailored.get("experience_projects", ""))

    md.append("\n# 需要你补充/确认的问题")
    for q in data.get("questions_to_clarify", []):
        md.append(f"- {q}")

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"[OK] Wrote: {args.out_md}")


if __name__ == "__main__":
    main()
