# AI Resume RAG（简历匹配 + RAG PoC，Chroma + OpenAI）

这是一个**可落地的最小可行项目（PoC）**：
- 用 **RAG** 把你的个人材料向量化（材料在本地 `data/`）
- 每次提供不同 **JD（岗位描述）**，用 **OpenAI** 生成：
  - 匹配要点（带“证据片段”）
  - 缺口与补强建议
  - 可直接粘贴到简历的定制段落（输出 Markdown）

> 重点：为避免仓库变大，**本项目不会把 `data/` 或 `data/index/` 上传到 GitHub**。

---

## 0. 仓库应该包含什么（你只提交这些）

建议提交：
- `src/`（代码）
- `requirements.txt`
- `.env.example`
- `README.md`
- `.gitignore`

不提交（强制）：
- `data/`（个人材料）
- `data/index/`（向量索引/向量库）
- `.venv/`

---

## 1. 环境准备（简单）

```bash
cd /root/.openclaw/workspace/ai-resume-rag
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. 配置 OpenAI（可切 OpenAI 兼容 base_url + 可切模型）

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：
- `BASE_URL`：例如 `https://api.openai.com/v1` 或你的网关地址
- `API_KEY`
- `MODEL_ID`：例如 `gpt-4o-mini`
- `EMBED_MODEL`：例如 `text-embedding-3-small`

（`PROVIDER` 只是展示字段，不影响请求；只要你的兼容服务满足 OpenAI 接口格式即可。）

---

## 3. 准备个人材料（放到本地 data/，不进 Git）

```bash
mkdir -p data/personal
```

把材料放到 `data/personal/`（支持 `.txt` / `.md`）：
- `resume_full.md`（简历全文文本，可复制整理）
- `projects.md`（项目经历）
- `skills.md`（技能清单）

> 你有 PDF 的话：先把 PDF 内容复制/导出为文本到 md/txt 再放进来。

---

## 4. 一次性建索引（输出到 data/index/，不进 Git）

```bash
python src/ingest.py \
  --input_dir data/personal \
  --persist_dir data/index
```

建完会得到：`data/index/`。

---

## 5. 启动服务（serve.py）

```bash
uvicorn src.serve:app --host 0.0.0.0 --port 8000
```

---

## 6. 按 JD 生成定制简历内容（输出 Markdown）

### 6.1 FastAPI 接口（可选）
POST `http://localhost:8000/match`

body 示例：
```json
{"jd":"岗位 JD 文本放这里","top_k":8}
```

### 6.2 CLI 直接生成 `output_match.md`（推荐）

先准备 `jd_sample.txt`（写入岗位 JD 文本）。

```bash
python src/match.py \
  --jd_file ./jd_sample.txt \
  --out_md ./output_match.md \
  --persist_dir data/index
```

输出 `output_match.md`，里面包含：
- 匹配要点（带证据片段）
- 缺口与补强建议
- 可直接粘贴到简历的 Markdown 段落

---

## 7. 简历里“AI 项目亮点”怎么写（可直接复制）

**AI 简历定制助手（RAG + LLM, PoC）**
- 基于个人材料构建本地 RAG：对简历/项目/技能文本分块并向量化，实现岗位相关证据检索。
- 每次输入不同 JD，通过检索证据增强生成，自动输出“匹配要点（带证据）/缺口与补强建议/定制简历段落（Markdown）”。
- 使用 OpenAI 模型生成结构化结果，并提供 FastAPI/CLI 用于快速按岗位定制投递内容。

---

## 8. GitHub 提交流程（保证不提交 data/.venv）

1）确保 `.gitignore` 存在并包含：
- `.venv/`
- `data/`
- `data/index/`

2）提交：
```bash
git add README.md requirements.txt src .env.example .gitignore
git commit -m "ai resume rag (chroma + openai)"
git push
```
