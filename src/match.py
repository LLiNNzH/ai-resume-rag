from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

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


COMMON_SKILL_HINTS = [
    "Python",
    "Java",
    "Go",
    "C++",
    "SQL",
    "Linux",
    "Docker",
    "Kubernetes",
    "FastAPI",
    "Flask",
    "Django",
    "Spring",
    "React",
    "Vue",
    "RAG",
    "LLM",
    "NLP",
    "数据分析",
    "算法",
]


def build_user_prompt(jd: str, retrieved_chunks: List[Dict[str, Any]]):
    joined = []
    for i, c in enumerate(retrieved_chunks, 1):
        joined.append(
            f"[材料片段{i}] (source={c.get('source','')})\n{c.get('text','')}"
        )
    context = "\n\n".join(joined)
    return f"JD如下：\n{jd}\n\n---\n已检索到的个人材料片段如下：\n{context}\n\n请生成定制简历内容。"


def _keyword_hits(text: str):
    lower = text.lower()
    hits = []
    for k in COMMON_SKILL_HINTS:
        if k.lower() in lower:
            hits.append(k)
    return hits[:8]


def generate_offline_result(jd: str, retrieved: List[Dict[str, Any]]):
    jd_keywords = _keyword_hits(jd)
    top_context = retrieved[0]["text"] if retrieved else ""
    evidence = top_context[:220] + ("..." if len(top_context) > 220 else "")

    matched_points = []
    for kw in jd_keywords[:3]:
        matched_points.append(
            {
                "point": f"具备与 {kw} 相关的实践或学习经验",
                "evidence_snippet": evidence or "本地材料中存在与岗位相关的描述",
                "why_matched": f"JD 中出现 {kw} 相关要求，材料中可检索到相关上下文。",
            }
        )

    if not matched_points:
        matched_points.append(
            {
                "point": "具备岗位相关的基础能力和项目表达能力",
                "evidence_snippet": evidence or "本地材料中存在可用于定制简历的内容",
                "why_matched": "基于检索到的个人材料生成的通用匹配点。",
            }
        )

    gaps = [
        {
            "gap": "缺少与 JD 完全逐字对应的项目表述",
            "suggestion": "在简历里补充具体技术栈、职责和量化结果。",
        }
    ]

    if jd_keywords:
        gaps.append(
            {
                "gap": f"岗位明确提到 {', '.join(jd_keywords[:3])}，需要进一步补充对应经历",
                "suggestion": "把与你最接近的项目经历改写成相同术语。",
            }
        )

    summary = """熟悉岗位定制化简历输出流程，能够基于个人材料与 JD 生成匹配要点、缺口和改写建议。"""
    if jd_keywords:
        summary = f"围绕 {', '.join(jd_keywords[:3])} 等岗位要求，定制简历表达并输出结构化结果。"

    skills = "、".join(jd_keywords[:6]) if jd_keywords else "Python、RAG、LLM、简历定制"

    experience_projects = """- 基于个人材料构建检索增强生成流程，输出可直接用于投递的 Markdown 简历片段。
- 通过本地向量检索召回相关证据，辅助岗位匹配和内容改写。"""

    return {
        "matched_points": matched_points,
        "gaps": gaps,
        "tailored_sections": {
            "summary": summary,
            "skills": skills,
            "experience_projects": experience_projects,
        },
        "questions_to_clarify": ["如果你愿意提供更完整的个人材料，定制结果会更精确。"],
    }


def generate_result(jd: str, retrieved: List[Dict[str, Any]]):
    client = build_client()
    if client is None:
        return generate_offline_result(jd, retrieved)

    resp = client.chat.completions.create(
        model=SETTINGS.model_id,
        messages=[
            {"role": "system", "content": MATCH_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(jd, retrieved)},
        ],
        temperature=0.2,
    )
    content = resp.choices[0].message.content
    return json.loads(content)


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
    data = generate_result(jd, retrieved)

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
