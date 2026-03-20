# ai-resume-rag（RAG 简历匹配 PoC，Chroma + OpenAI）

可运行的简历定制 PoC（输出 Markdown）。
- 个人材料放本地 `data/personal/`（不提交到 GitHub）
- 向量索引输出到本地 `data/index/`（不提交到 GitHub）
- 代码 + README 发布到 GitHub

---

## 0) Python 版本
建议用 **Python 3.9**。

---

## 1) 环境准备

```bash
cd /path/to/ai-resume-rag
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2) 配置 OpenAI（或 OpenAI 兼容 base_url）

```bash
cp .env.example .env
```

`.env` 里至少填写：
- `BASE_URL`：例如 `https://api.openai.com/v1`
- `API_KEY`
- `MODEL_ID`：如 `gpt-4o-mini`
- `EMBED_MODEL`：如 `text-embedding-3-small`

---

## 3) 准备材料（本地，不进仓库）

```bash
mkdir -p data/personal
```

放入：
- `resume_full.md`（简历全文文本）
- `projects.md`
- `skills.md`

支持 `.md` / `.txt`。

---

## 4) 建索引（一次性）

> 注意：从仓库根目录执行，用 `-m` 方式运行，保证 `src` 包导入正常。

```bash
python -m src.ingest \
  --input_dir data/personal \
  --persist_dir data/index
```

---

## 5) 按 JD 生成结果（输出 Markdown）

1）写 `jd_sample.txt`（粘贴岗位 JD）

2）运行：

```bash
python -m src.match \
  --jd_file ./jd_sample.txt \
  --out_md ./output_match.md \
  --persist_dir data/index
```

输出：`output_match.md`

---

## 6) 可选：启动服务

```bash
uvicorn src.serve:app --host 0.0.0.0 --port 8000
```

POST `http://localhost:8000/match`，body 示例：
```json
{"jd":"岗位JD文本","top_k":8}
```

---

## 7) GitHub 提交流程（不提交 data/.venv）
确认 `.gitignore` 已忽略：
- `.venv/`
- `data/`
- `data/index/`

提交代码：
```bash
git add README.md requirements.txt src .env.example .gitignore
git commit -m "init ai-resume-rag (no data)"
git push
```
