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

#### Verbose 模式（忠于原文的详细改写）

默认模式会生成精简版教程（~20% 原文篇幅）。如果需要保留原文几乎所有技术细节，启用 `--verbose-mode`：

```bash
python -m cli batch MYBOOK --verbose-mode
```

Verbose 模式会：
- 利用 PDF TOC 的层级结构**自适应分节**（L2 不够就展开 L3/L4）
- 逐节调用 LLM 进行**忠实改写**（非压缩总结）
- 每节输出为独立文件 `ch{x}_{y}.md`，并生成 `ch{x}.md` 索引页

> **注意**：Verose 模式需要 `chapters_raw.json` 包含 TOC 数据。如果已有数据缺少 TOC，请重新运行 `parse` 命令。

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

#### Verbose Mode (faithful detailed rewrite)

Default mode produces condensed tutorials (~20% of original length). For preserving nearly all technical details, enable `--verbose-mode`:

```bash
python -m cli batch MYBOOK --verbose-mode
```

Verbose mode:
- **Adaptive section splitting** using PDF TOC hierarchy (L2 → L3 → L4 as needed)
- **Faithful rewrite** per section (not a summary)
- Outputs each section as a separate file `ch{x}_{y}.md` with a `ch{x}.md` index page

> **Note**: Verbose mode requires TOC data in `chapters_raw.json`. Re-run `parse` if your data lacks TOC.

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
