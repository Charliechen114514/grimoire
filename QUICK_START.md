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
pip install -e .            # 默认：解析 + LLM 生成（不含 OCR）
# pip install -e ".[all]"   # 全部依赖（含 OCR、站点打包、开发）
```

### 2. 配置 API 密钥

在项目根目录创建 `.env` 文件：

```bash
ANTHROPIC_API_KEY=你的API密钥
# ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic   # 可选：代理地址
# GRIMOIRE_MODEL=sonnet   # 可选：默认模型 tier (haiku/sonnet/opus)
```

默认使用 `sonnet` tier。可通过 `--model` CLI 参数或 `GRIMOIRE_MODEL` 环境变量切换，详见下方「模型选择」。

### 3. 准备 PDF

将 PDF 教材放入 `books/` 目录。PDF 必须有目录（TOC），且条目需包含 "Chapter N" 格式的章节标题。

### 4. 解析

```bash
# PDF 教材
python -m cli parse books/your-book.pdf --slug MYBOOK

# Wolai 页面（自动检测引擎，秒级解析）
python -m cli parse https://www.wolai.com/fkGSwxLu2pjWD7kiBY1V7W --slug RTR4

# 指定 Web 引擎
python -m cli parse https://example.com/tutorial --slug MYBOOK --engine static
python -m cli parse https://spa.example.com --slug MYBOOK --engine playwright
```

### 5. 批量生成教程

```bash
python -m cli batch MYBOOK              # 断点续跑
python -m cli batch MYBOOK --no-resume  # 从头开始
```

每章经过 4 个 Agent：Concept → Writing + Exercise（并行）→ TLDR。可随时 Ctrl+C 中断，重跑自动跳过已完成章节。

#### 并行加速

使用 `--workers N` 并行处理多个章节，显著缩短总耗时：

```bash
python -m cli batch MYBOOK --workers 4          # 4 章并行
python -m cli all books/book.pdf --slug MYBOOK -w 4  # 全管线并行
```

- 默认 `--workers 1` 为串行（与之前行为一致）
- 并行时使用 glossary 快照策略，每章完成后延迟合并新概念
- 全局 API 并发信号量自动控制请求速率，配合指数退避双重保护
- 环境变量 `MAX_CONCURRENT_CHAPTERS` 可设置默认值（默认 4）

#### Verbose 模式（忠于原文的详细改写）

默认模式会生成精简版教程（~20% 原文篇幅）。如果需要保留原文几乎所有技术细节，启用 `--verbose-mode`：

```bash
python -m cli batch MYBOOK --verbose-mode
```

Verbose 模式会：
- 利用 PDF TOC 的层级结构**自适应分节**（L2 不够就展开 L3/L4）
- 逐节调用 LLM 进行**忠实改写**（非压缩总结）
- 每节输出为独立文件 `ch{x}_{y}.md`，并生成 `ch{x}.md` 索引页

> **注意**：Verbose 模式需要 `chapters_raw.json` 包含 TOC 数据。如果已有数据缺少 TOC，请重新运行 `parse` 命令。

#### 大章节自动分割（防截断）

对于 Wolai 等 Web 来源，即使不开启 `--verbose-mode`，管线也会**自动检测大章节并分节处理**：

- 当原文包含 Markdown 标题（如 `### 12.1 图像处理`）时，自动按标题切分
- 切分后逐节调用 LLM 生成，避免单次输出 token 不够导致**内容截断**
- 无需手动配置，对小章节（无可识别标题）无影响

此机制对 PDF 来源同样安全——PDF 的 pymupdf TOC 通常已包含多级条目，会优先使用 TOC 分节。

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

### 模型选择

`batch` 和 `all` 命令支持 `--model` / `-m` 参数：

```bash
python -m cli batch MYBOOK --model haiku    # 快速/低成本
python -m cli batch MYBOOK --model opus     # 最高质量
python -m cli batch MYBOOK --model glm-5.1  # 直接指定模型名
```

**优先级**：`--model` CLI 参数 > `GRIMOIRE_MODEL` 环境变量 > 默认 `sonnet`

| Alias | 环境变量映射 | 默认值 |
|---|---|---|
| `haiku` | `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `claude-haiku-4-5-20251001` |
| `sonnet` | `ANTHROPIC_DEFAULT_SONNET_MODEL` | `claude-sonnet-4-6-20250514` |
| `opus` | `ANTHROPIC_DEFAULT_OPUS_MODEL` | `claude-opus-4-6-20250514` |

> 配合 `ANTHROPIC_BASE_URL` 使用第三方代理时，设置对应的环境变量即可映射到实际模型名（如 `ANTHROPIC_DEFAULT_HAIKU_MODEL=GLM-4.7`）。

### 自定义写作风格

生成教程的人格和语气由 `config/writing_style.md` 控制。项目自带默认风格（SICP 叙事风），可直接使用。

如需调整，可从模板起步：

```bash
# 查看可用模板
ls config/writing_style*.template*

# 选择一个模板覆盖默认配置（二选一）
cp config/writing_style1.template.md config/writing_style.md   # 模板 1
cp config/writing_style2.template config/writing_style.md       # 模板 2

# 然后按需编辑
vim config/writing_style.md
```

- **模板 1**（`writing_style1.template.md`）：SICP 教材叙事风（与当前默认一致）
- **模板 2**（`writing_style2.template`）：工程师博客实战风

> 也可以直接编辑 `config/writing_style.md`，不依赖模板。文件为纯 Markdown，内容越详细，生成的教程风格越一致。

### 其他自定义

| 改什么 | 在哪里 |
|---|---|
| Agent 提示词 | `prompts/system/*.md`、`prompts/user/*.md` |
| 模型配置 | `--model` 参数、`GRIMOIRE_MODEL` 环境变量 |
| 并发章节数 | `--workers N` 或 `MAX_CONCURRENT_CHAPTERS` 环境变量 |
| Web 解析引擎 | `--engine name` 或自定义 `src/parsers/engines/` |

### 一条龙

```bash
# PDF 教材
python -m cli all books/textbook.pdf --slug MYBOOK   # parse → batch → review → package

# Wolai 教材（4 章并行）
python cli.py all "https://www.wolai.com/fkGSwxLu2pjWD7kiBY1V7W" --slug RTR4 --workers 4
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
pip install -e .            # Default: parse + LLM generation (no OCR)
# pip install -e ".[all]"   # All dependencies (OCR, site packaging, dev)
```

### 2. Configure API Key

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your-api-key-here
# ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic   # Optional: proxy URL
# GRIMOIRE_MODEL=sonnet   # Optional: default model tier (haiku/sonnet/opus)
```

Default model tier is `sonnet`. Switch via `--model` CLI flag or `GRIMOIRE_MODEL` env var — see "Model Selection" below.

### 3. Prepare PDF

Place your PDF textbook in `books/`. The PDF must have a TOC with "Chapter N" entries.

### 4. Parse

```bash
# PDF textbook
python -m cli parse books/your-book.pdf --slug MYBOOK

# Wolai page (auto-detected engine, instant parsing)
python -m cli parse https://www.wolai.com/fkGSwxLu2pjWD7kiBY1V7W --slug RTR4

# Specify web engine
python -m cli parse https://example.com/tutorial --slug MYBOOK --engine static
python -m cli parse https://spa.example.com --slug MYBOOK --engine playwright
```

### 5. Batch Generate Tutorials

```bash
python -m cli batch MYBOOK              # Resume from checkpoint
python -m cli batch MYBOOK --no-resume  # Start fresh
```

Each chapter goes through 4 agents: Concept → Writing + Exercise (parallel) → TLDR. Safe to Ctrl+C and resume later.

#### Parallel Acceleration

Use `--workers N` to process multiple chapters concurrently:

```bash
python -m cli batch MYBOOK --workers 4          # 4 chapters in parallel
python -m cli all books/book.pdf --slug MYBOOK -w 4  # Full pipeline parallel
```

- Default `--workers 1` is sequential (same as before)
- Uses glossary snapshot strategy with late merge for parallel chapters
- Global API semaphore controls concurrent requests with exponential backoff
- Environment variable `MAX_CONCURRENT_CHAPTERS` sets default (default: 4)

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

#### Auto-splitting for large chapters (truncation prevention)

For web sources like Wolai, the pipeline **automatically detects and splits large chapters** even without `--verbose-mode`:

- Scans raw text for Markdown headings (e.g. `### 12.1 Image Processing`) and splits by them
- Each section is processed separately by the LLM, preventing **content truncation** from output token limits
- No manual configuration needed; small chapters without detectable headings are unaffected

This is safe for PDF sources too — pymupdf TOC usually already contains multi-level entries, which take priority over text-based splitting.

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

### Model Selection

`batch` and `all` commands support `--model` / `-m`:

```bash
python -m cli batch MYBOOK --model haiku    # Fast / low cost
python -m cli batch MYBOOK --model opus     # Highest quality
python -m cli batch MYBOOK --model glm-5.1  # Direct model name
```

**Priority**: `--model` CLI flag > `GRIMOIRE_MODEL` env var > default `sonnet`

| Alias | Env var mapping | Default |
|---|---|---|
| `haiku` | `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `claude-haiku-4-5-20251001` |
| `sonnet` | `ANTHROPIC_DEFAULT_SONNET_MODEL` | `claude-sonnet-4-6-20250514` |
| `opus` | `ANTHROPIC_DEFAULT_OPUS_MODEL` | `claude-opus-4-6-20250514` |

> When using a third-party proxy via `ANTHROPIC_BASE_URL`, set the env vars to map to actual model names (e.g., `ANTHROPIC_DEFAULT_HAIKU_MODEL=GLM-4.7`).

### Customize Writing Style

The persona and tone of generated tutorials are controlled by `config/writing_style.md`. A default style (SICP narrative) ships with the project and works out of the box.

To customize, start from a template:

```bash
# List available templates
ls config/writing_style*.template*

# Pick one and overwrite the default
cp config/writing_style1.template.md config/writing_style.md   # Template 1
cp config/writing_style2.template config/writing_style.md       # Template 2

# Edit to your liking
vim config/writing_style.md
```

- **Template 1** (`writing_style1.template.md`): SICP textbook narrative style (same as current default)
- **Template 2** (`writing_style2.template`): Engineer blog / hands-on style

> You can also edit `config/writing_style.md` directly without a template. The file is plain Markdown — the more detailed it is, the more consistent the generated tutorials will be.

### Other Customization

| What to change | Where |
|---|---|
| Agent prompts | `prompts/system/*.md`, `prompts/user/*.md` |
| Model config | `--model` flag, `GRIMOIRE_MODEL` env var |
| Concurrency | `--workers N` or `MAX_CONCURRENT_CHAPTERS` env var |

### All-in-one

```bash
# PDF textbook
python -m cli all books/textbook.pdf --slug MYBOOK   # parse → batch → review → package

# Wolai textbook (4 chapters in parallel)
python cli.py all "https://www.wolai.com/fkGSwxLu2pjWD7kiBY1V7W" --slug RTR4 --workers 4
```

Add `-v` for debug logging.
