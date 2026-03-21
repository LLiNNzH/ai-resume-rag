# ai-resume-rag（简历 JD 对齐与自动优化）

这是一个面向求职场景的简历定制工具。

用户输入：
- 原始简历材料（本地 `data/personal/`）
- 目标岗位 JD（`jd_sample.txt` 或接口传入）

系统输出：
- 一份完整的岗位定制版简历 Markdown

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

## 3) 准备材料

```bash
mkdir -p data/personal
```

放入：
- `resume_full.md`（简历全文文本）
- `projects.md`（其他一些材料）
- `skills.md`（其他一些材料）

支持 `.md` / `.txt`。

---

## 4) 建索引（一次性）

> 注意：从仓库根目录执行，用 `-m` 方式运行

```bash
python3.9 -m src.ingest \
  --input_dir data/personal \
  --persist_dir data/index
```

---

## 5) 按 JD 生成完整简历（输出 Markdown）

1）写 `jd_sample.txt`（粘贴岗位 JD）

2）运行：

```bash
python3.9 -m src.match \
  --jd_file ./jd_sample.txt \
  --out_md ./output_match.md \
  --persist_dir data/index
```

输出：`output_match.md`

这个文件就是最终的岗位定制版简历。

---

## 6) 可选：启动服务

```bash
uvicorn src.serve:app --host 0.0.0.0 --port 8000
```

POST `http://localhost:8000/match`，body 示例：
```json
{"jd":"岗位JD文本","top_k":8}
```

返回：
```json
{"resume_markdown":"...完整简历正文..."}
```

提交代码：
```bash
git add README.md requirements.txt src .env.example .gitignore
git commit -m "refine resume jd optimization flow"
git push
```
