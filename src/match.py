from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List

from src.settings import SETTINGS
from src.embed_store import LocalChromaStore
from src.openai_client import build_client


RESUME_SYSTEM_PROMPT = """你是一个资深求职简历改写器。
你的任务只有一个：根据目标岗位 JD 和检索到的个人材料，输出一份“完整、可直接投递”的岗位定制简历。

硬性要求：
- 只输出简历正文，不要输出任何解释、分析、提示词痕迹、评分、缺口、建议、证据列表。
- 只能基于输入材料改写，不要编造不存在的经历、项目、学校、公司、技能或成果。
- 如果某项信息不明确，宁可省略或保守表达，也不要乱补。
- 输出必须是 Markdown，结构清晰，像真实简历成品。
- 尽量让内容完整：包括姓名/联系方式、教育经历、技能、项目经历、实习/工作经历、自我评价等。
- 如果材料中没有某个模块，就不要硬造；可以不写该模块。
- 语言要自然、专业、像真实投递版简历，不要像模型说明书。
- 优先对齐 JD 的关键词和职责，但必须保持事实真实。

输出格式要求：
- 直接输出一份 Markdown 简历正文。
- 不要输出 JSON，不要输出代码块，不要输出任何前后缀说明。
"""


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|td|th|section|article|ul|ol)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


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


def _truncate(text: str, limit: int = 1200) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _select_context_blocks(retrieved_chunks: List[Dict[str, Any]], max_chars: int = 6500) -> str:
    blocks = []
    total = 0
    for i, c in enumerate(_dedupe_chunks(retrieved_chunks), 1):
        source = c.get("source", "")
        text = _clean_text(c.get("text", ""))
        if not text:
            continue
        block = f"[材料片段{i}] source={source}\n{text}"
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining > 200:
                block = block[:remaining]
                blocks.append(block)
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks) if blocks else "（未检索到可用个人材料）"


def build_user_prompt(jd: str, retrieved_chunks: List[Dict[str, Any]]):
    context = _select_context_blocks(retrieved_chunks)
    return (
        "目标岗位 JD:\n"
        f"{_clean_text(jd)}\n\n"
        "个人材料片段:\n"
        f"{context}\n\n"
        "请基于以上信息，直接输出一份完整的岗位定制版简历 Markdown。"
        "注意：不要输出解释、不要输出分析、不要输出任何提词器痕迹。"
    )


def _strip_wrappers(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md|json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    # remove obvious leftover prompt labels if the model leaks them
    text = re.sub(r"(?m)^\s*[-*]?\s*(要点|缺口|建议|证据|匹配原因|Summary|Skills|Experience/Projects|Resume Version|Preservation Notes)\s*[:：].*$", "", text)
    text = re.sub(r"(?m)^\s*#\s*JD 对齐要点.*$", "", text)
    text = re.sub(r"(?m)^\s*#\s*缺口与补强建议.*$", "", text)
    return text.strip()


def _normalize_model_output(content: str) -> str:
    content = _strip_wrappers(content)
    content = _clean_text(content)
    # keep markdown structure but remove accidental huge HTML fragments
    content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.S | re.I)
    content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.S | re.I)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def _fallback_resume(jd: str, retrieved: List[Dict[str, Any]]) -> str:
    retrieved = _dedupe_chunks(retrieved)
    blocks = []
    for c in retrieved[:6]:
        text = _clean_text(c.get("text", ""))
        if text:
            blocks.append(text)

    merged = "\n\n".join(blocks) if blocks else ""
    merged = _truncate(merged, 5000)
    if not merged:
        merged = "（未检索到足够材料，建议补充完整简历文本后重新生成）"

    return (
        "# 林子豪\n\n"
        "## 个人简介\n"
        "基于目标岗位 JD 的简历定制版本。\n\n"
        "## 教育经历\n"
        f"{merged}\n"
    )


def generate_resume(jd: str, retrieved: List[Dict[str, Any]]) -> str:
    client = build_client()
    if client is None:
        return _fallback_resume(jd, retrieved)

    resp = client.chat.completions.create(
        model=SETTINGS.model_id,
        messages=[
            {"role": "system", "content": RESUME_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(jd, retrieved)},
        ],
        temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    cleaned = _normalize_model_output(content)
    if not cleaned:
        return _fallback_resume(jd, retrieved)
    return cleaned


def generate_result(jd: str, retrieved: List[Dict[str, Any]]):
    resume_markdown = generate_resume(jd, retrieved)
    return {
        "resume_markdown": resume_markdown,
        "resume_plaintext": _clean_text(re.sub(r"[#*_`>\"]", " ", resume_markdown)),
    }


def _render_markdown(data: Dict[str, Any]) -> str:
    return data.get("resume_markdown", "")


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
