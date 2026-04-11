# Quick Start / 快速上手

**[中文](#qs-zh) | [English](#qs-en)**

---

<a id="qs-zh"></a>

## 快速上手

5 分钟从 clone 到生成你的第一个教程。

### 1. 安装

```bash
git clone https://github.com/charliechen114514/grimoire.git
cd grimoire
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API 密钥

在项目根目录创建 `.env` 文件：

```bash
ANTHROPIC_API_KEY=你的API密钥
# ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic   # 可选：代理地址
```

当前模型为 `claude-sonnet-4-6-20250514`，可在 `src/config.py` 中修改。

### 3. 准备 PDF

将 PDF 教材放入 `books/` 目录。PDF 必须有目录（TOC），且条目需包含 "Chapter N" 格式的章节标题。

### 4. 解析

```bash
python -m cli parse books/your-book.pdf --slug MYBOOK
```

### 5. 批量生成教程

```bash
python -m cli batch MYBOOK              # 断点续跑
python -m cli batch MYBOOK --no-resume  # 从头开始
```

每章经过 4 个 Agent：Concept → Writing → Exercise → TLDR。可随时 Ctrl+C 中断，重跑自动跳过已完成章节。

### 6. 打包为网站

```bash
python -m cli package MYBOOK
cd output/MYBOOK && mkdocs serve   # 预览 http://127.0.0.1:8000
```

### 7. 质量审核（可选）

```bash
python -m cli review MYBOOK              # 全部章节
python -m cli review MYBOOK --chapters 1 2  # 指定章节
```

### 自定义

| 改什么 | 在哪里 |
|---|---|
| 写作人格 | `config/writing_style.md` |
| Agent 提示词 | `prompts/system/*.md`、`prompts/user/*.md` |
| 模型配置 | `src/config.py` |

### 一条龙

```bash
python -m cli all books/textbook.pdf --slug MYBOOK   # parse → batch → review → package
```

加 `-v` 查看 debug 日志。

---

<a id="qs-en"></a>

## Quick Start

From clone to your first tutorial in 5 minutes.

### 1. Install

```bash
git clone https://github.com/charliechen114514/grimoire.git
cd grimoire
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your-api-key-here
# ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic   # Optional: proxy URL
```

Default model is `claude-sonnet-4-6-20250514`. Change it in `src/config.py`.

### 3. Prepare PDF

Place your PDF textbook in `books/`. The PDF must have a TOC with "Chapter N" entries.

### 4. Parse

```bash
python -m cli parse books/your-book.pdf --slug MYBOOK
```

### 5. Batch Generate Tutorials

```bash
python -m cli batch MYBOOK              # Resume from checkpoint
python -m cli batch MYBOOK --no-resume  # Start fresh
```

Each chapter goes through 4 agents: Concept → Writing → Exercise → TLDR. Safe to Ctrl+C and resume later.

### 6. Package as Website

```bash
python -m cli package MYBOOK
cd output/MYBOOK && mkdocs serve   # Preview at http://127.0.0.1:8000
```

### 7. Quality Review (Optional)

```bash
python -m cli review MYBOOK              # All chapters
python -m cli review MYBOOK --chapters 1 2  # Specific chapters
```

### Customization

| What to change | Where |
|---|---|
| Writing persona | `config/writing_style.md` |
| Agent prompts | `prompts/system/*.md`, `prompts/user/*.md` |
| Model config | `src/config.py` |

### All-in-one

```bash
python -m cli all books/textbook.pdf --slug MYBOOK   # parse → batch → review → package
```

Add `-v` for debug logging.
