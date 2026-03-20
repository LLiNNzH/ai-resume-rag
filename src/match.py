from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore
from src.openai_client import build_client


MATCH_SYSTEM_PROMPT = """你是一个资深求职简历优化器。
你的目标不是“抽取资料”，而是：
1) 基于已检索到的个人材料，按目标岗位重新优化简历表达；
2) 保留原简历里已经有的强项，不要无缘无故删掉亮点；
3) 在不编造事实的前提下，把内容改写得更贴合岗位、更像真实投递版本；
4) 如果某项信息不足，宁可保持保守、提示补充，也不要夸大或伪造。

硬性要求：
- 只能使用已检索到的材料和 JD 中明确给出的要求。
- 所有“成果/职责/技术”必须能从材料中找到依据。
- 如果某个点无法确认，写进 questions_to_clarify，而不是猜。
- 改写时优先：保留原事实 > 岗位化重排 > 语言增强 > 量化表达（只有在材料支持时才能量化）。
- 不要把简历越改越短；如果某一段原本有价值，改写后应至少保留相同信息密度。

输出必须是 JSON，不要夹带任何解释文字。结构如下：
{
  "matched_points": [
    {
      "point": "与岗位匹配的能力点",
      "evidence_snippet": "从材料中直接摘取或近义复述的证据",
      "why_matched": "为什么这个点与 JD 匹配"
    }
  ],
  "gaps": [
    {
      "gap": "JD 要求但材料里不够明确的部分",
      "suggestion": "如何补充或如何在简历里保守表达"
    }
  ],
  "tailored_sections": {
    "summary": "适合投递该岗位的简历摘要",
    "skills": "按岗位重排后的技能清单",
    "experience_projects": "按岗位优化后的项目/经历表述",
    "resume_version": "一个可以直接粘贴进简历的精简版本",
    "preservation_notes": "明确说明保留了哪些原简历亮点"
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
    "机器学习",
    "深度学习",
    "数据分析",
    "算法",
    "后端",
    "前端",
    "测试",
    "分布式",
    "微服务",
]


def build_user_prompt(jd: str, retrieved_chunks: List[Dict[str, Any]]):
    joined = []
    for i, c in enumerate(retrieved_chunks, 1):
        joined.append(
            f"[材料片段{i}] (source={c.get('source','')}, distance={c.get('distance','')})\n{c.get('text','')}"
        )
    context = "\n\n".join(joined) if joined else "（没有检索到材料片段）"
    return (
        f"JD如下：\n{jd}\n\n"
        f"---\n已检索到的个人材料片段如下：\n{context}\n\n"
        "请基于这些材料生成岗位定制版简历内容。"
    )


def _keyword_hits(text: str):
    lower = text.lower()
    hits = []
    for k in COMMON_SKILL_HINTS:
        if k.lower() in lower:
            hits.append(k)
    return hits[:8]


def _dedupe_chunks(chunks: List[Dict[str, Any]]):
    seen = set()
    out = []
    for c in chunks:
        key = (c.get("source", ""), c.get("text", "").strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _shorten(text: str, limit: int = 220):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _extract_json(text: str):
    text = text.strip()
    # 先尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass

    # 再从 fenced code 中取 JSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))

    # 最后尝试截取第一个大括号到最后一个大括号
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("Model output is not valid JSON")


def generate_offline_result(jd: str, retrieved: List[Dict[str, Any]]):
    retrieved = _dedupe_chunks(retrieved)
    jd_keywords = _keyword_hits(jd)
    top_context = retrieved[0]["text"] if retrieved else ""
    evidence = _shorten(top_context, 260) if top_context else "本地材料中存在可用于定制简历的内容"

    matched_points = []
    for kw in jd_keywords[:4]:
        matched_points.append(
            {
                "point": f"围绕 {kw} 的相关经验/表达方式",
                "evidence_snippet": evidence,
                "why_matched": f"JD 中出现 {kw} 相关要求，材料中可以基于检索片段进行保守改写。",
            }
        )

    if not matched_points:
        matched_points.append(
            {
                "point": "保留原有项目/经历的核心亮点，并重写为更适合投递的表达",
                "evidence_snippet": evidence,
                "why_matched": "没有强关键词时，优先做保守重写，避免比原简历更差。",
            }
        )

    gaps = [
        {
            "gap": "材料中部分经历可能还缺少岗位直连的术语和量化结果",
            "suggestion": "在简历里保留原事实的基础上，补充技术栈、职责边界和结果描述。",
        },
        {
            "gap": "JD 要求与原简历表述之间可能存在措辞不一致",
            "suggestion": "把同一个经历改写成更接近 JD 关键词的版本，但不要新增未经证实的能力。",
        },
    ]

    if jd_keywords:
        gaps.append(
            {
                "gap": f"岗位显式要求：{', '.join(jd_keywords[:3])}",
                "suggestion": "优先把你最强的那一段经历改写成这些关键词出现的版本。",
            }
        )

    summary = (
        "本版本优先保留原简历亮点，再根据岗位要求重排内容与措辞，输出更适合投递的简历摘要。"
    )
    if jd_keywords:
        summary = (
            f"围绕 {', '.join(jd_keywords[:3])} 等岗位要求，保留原有亮点并做岗位化重写。"
        )

    skills = "、".join(jd_keywords[:6]) if jd_keywords else "Python、RAG、LLM、简历定制"

    if retrieved:
        top_bullets = []
        for idx, c in enumerate(retrieved[:3], 1):
            top_bullets.append(
                f"{idx}. {_shorten(c.get('text',''), 120)}"
            )
        experience_projects = (
            "- 基于个人材料构建检索增强简历定制流程，按岗位要求重写投递内容。\n"
            "- 保留原简历已有亮点，并在不改变事实的前提下增强岗位匹配度。\n"
            + "\n".join(f"- {b}" for b in top_bullets)
        )
    else:
        experience_projects = (
            "- 基于个人材料构建检索增强简历定制流程，按岗位要求重写投递内容。\n"
            "- 保留原简历已有亮点，并在不改变事实的前提下增强岗位匹配度。"
        )

    resume_version = (
        f"【简历摘要】{summary}\n"
        f"【技能】{skills}\n"
        f"【经历/项目】{_shorten(experience_projects, 350)}"
    )

    preservation_notes = (
        "1. 保留了原材料中可确认的核心经历；2. 未添加无法验证的成果；3. 优先使用岗位关键词重排表达，而不是删减内容。"
    )

    return {
        "matched_points": matched_points,
        "gaps": gaps,
        "tailored_sections": {
            "summary": summary,
            "skills": skills,
            "experience_projects": experience_projects,
            "resume_version": resume_version,
            "preservation_notes": preservation_notes,
        },
        "questions_to_clarify": [
            "如果你提供完整简历原文和目标岗位 JD，定制效果会更好。",
            "如果某段经历有量化结果，补上后会显著提升简历质量。",
        ],
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
    content = resp.choices[0].message.content or "{}"
    return _extract_json(content)


def _render_markdown(data: Dict[str, Any]) -> str:
    md: List[str] = []
    md.append("# 匹配要点（带证据）")
    for x in data.get("matched_points", []):
        md.append(
            f"- **要点**：{x.get('point','')}\n"
            f"  - **证据**：{x.get('evidence_snippet','')}\n"
            f"  - **匹配原因**：{x.get('why_matched','')}"
        )

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
    md.append("\n## Resume Version")
    md.append(tailored.get("resume_version", ""))
    md.append("\n## Preservation Notes")
    md.append(tailored.get("preservation_notes", ""))

    md.append("\n# 需要你补充/确认的问题")
    for q in data.get("questions_to_clarify", []):
        md.append(f"- {q}")

    return "\n".join(md)


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
    md = _render_markdown(data)

    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[OK] Wrote: {args.out_md}")


if __name__ == "__main__":
    main()
