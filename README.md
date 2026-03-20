# ai-resume-rag（RAG 简历匹配 PoC，Chroma + OpenAI）

这是一个**开箱即用的简历定制 PoC**：
- 你把个人材料放到 `data/personal/`（本地，不提交 GitHub）
- `ingest.py` 把材料向量化进 `data/index/`（本地，不提交）
- 每次输入 JD，`match.py` 调用 OpenAI 生成**按岗位定制的 Markdown**（含：匹配要点/缺口/建议）

---

## 0. 环境准备

```bash
cd /root/.openclaw/workspace/ai-resume-rag
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 1. 配置 OpenAI（或 OpenAI 兼容 base_url）

```bash
cp .env.example .env
```

编辑 `.env`（最少需要）：
- `BASE_URL`：例如 `https://api.openai.com/v1` 或你的网关
- `API_KEY`
- `MODEL_ID`：例如 `gpt-4o-mini`
- `EMBED_MODEL`：例如 `text-embedding-3-small`

---

## 2. 放材料（本地，不进仓库）

```bash
mkdir -p data/personal
```

把文本材料放进去（支持 `.md` / `.txt`）：
- `resume_full.md`：简历全文（建议直接复制文本整理）
- `projects.md`：项目经历
- `skills.md`：技能清单

---

## 3. 建索引（一次性）

```bash
python src/ingest.py \
  --input_dir data/personal \
  --persist_dir data/index
```

---

## 4. 生成定制结果（每次投递）

### 4.1 准备 JD 文件
新建 `jd_sample.txt`，粘贴岗位 JD。

### 4.2 运行匹配，输出 Markdown

```bash
python src/match.py \
  --jd_file ./jd_sample.txt \
  --out_md ./output_match.md \
  --persist_dir data/index
```

输出：`output_match.md`，结构如下：
- `# 匹配要点（带证据）`
- `# 缺口与补强建议`
- `# 可直接粘贴到简历的定制段落（Markdown）`

你直接复制粘贴到简历/Word/飞书文档即可。

---

## 5. （可选）启动服务

```bash
uvicorn src.serve:app --host 0.0.0.0 --port 8000
```

调用接口：
- `POST http://localhost:8000/match`

请求体示例：
```json
{"jd":"岗位JD文本放这里","top_k":8}
```

---

## 6. GitHub 提交流程（不会提交 data/.venv）

本仓库已配置 `.gitignore`，确保不提交：
- `.venv/`
- `data/`
- `data/index/`

提交命令：
```bash
git add README.md requirements.txt src .env.example .gitignore
git commit -m "init"
git push
```
