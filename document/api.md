# Usage / 使用指南

## Installation

```bash
git clone https://github.com/charliechen114514/grimoire.git
cd grimoire
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .            # Default: parse + LLM generation (no OCR)
# pip install -e ".[all]"   # All dependencies (OCR, site packaging, dev)
```

### API Key Configuration / API 密钥配置

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your-api-key-here
ANTHROPIC_BASE_URL=https://optional-proxy.example.com/api/anthropic
# GRIMOIRE_MODEL=sonnet   # Optional: default model tier (haiku/sonnet/opus)
```

- `ANTHROPIC_API_KEY` — Required. Your Anthropic API key.
- `ANTHROPIC_BASE_URL` — Optional. Proxy endpoint (e.g., `https://open.bigmodel.cn/api/anthropic`). Defaults to Anthropic's official API.
- `GRIMOIRE_MODEL` — Optional. Default model tier (`haiku`/`sonnet`/`opus`). Defaults to `sonnet`.

## CLI Commands

All commands go through a unified CLI (`python -m cli`).

### Full Pipeline (recommended)

```bash
python -m cli all books/textbook.pdf --slug MYBOOK
```

### Phase 1: Parse PDF / 解析 PDF

```bash
python -m cli parse books/your-textbook.pdf --slug MYBOOK
```

This creates `data/MYBOOK/chapters_raw.json`.

### Phase 2: Generate Tutorials / 批量生成

```bash
python -m cli batch MYBOOK              # Resume from last checkpoint (default)
python -m cli batch MYBOOK --no-resume  # Start fresh
```

Progress is saved after each chapter — safe to interrupt and resume.

#### Model Selection / 模型选择

Use `--model` (or `-m`) to select model via alias or direct name:

```bash
python -m cli batch MYBOOK --model haiku    # Fast / low cost
python -m cli batch MYBOOK --model opus     # Highest quality
python -m cli batch MYBOOK --model glm-5.1  # Direct model name
```

**Priority**: `--model` CLI flag > `GRIMOIRE_MODEL` env var > default `sonnet`

| Alias | Env var mapping | Default value |
|---|---|---|
| `haiku` | `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `claude-haiku-4-5-20251001` |
| `sonnet` | `ANTHROPIC_DEFAULT_SONNET_MODEL` | `claude-sonnet-4-6-20250514` |
| `opus` | `ANTHROPIC_DEFAULT_OPUS_MODEL` | `claude-opus-4-6-20250514` |

> When using a proxy via `ANTHROPIC_BASE_URL`, map aliases to actual model names via the `ANTHROPIC_DEFAULT_*_MODEL` env vars.

#### Parallel Processing / 并行加速

Use `--workers N` (or `-w N`) to process multiple chapters concurrently:

```bash
python -m cli batch MYBOOK --workers 4         # 4 chapters in parallel
python -m cli batch MYBOOK -w 2 --verbose-mode  # 2 chapters parallel + verbose
```

- Default `--workers 1` is sequential (identical to previous behavior)
- Within each chapter, Writing + Exercise agents also run in parallel
- Set default via environment variable: `MAX_CONCURRENT_CHAPTERS=4`
- Full pipeline also supports `--workers`: `python -m cli all books/book.pdf --slug MYBOOK -w 4`

#### Verbose Mode / 详细模式

Add `--verbose-mode` for faithful, detailed rewrites that preserve nearly all technical content:

```bash
python -m cli batch MYBOOK --verbose-mode
python -m cli batch MYBOOK --verbose-mode --no-resume  # Fresh start in verbose mode
```

Verbose mode splits each chapter into sections based on the PDF's TOC hierarchy, then rewrites each section separately. Output is one file per section (`ch{NN}_{S}.md`) plus an index page (`ch{NN}.md`).

> **Prerequisite**: Requires TOC data in `chapters_raw.json`. If you see a warning about missing TOC, re-run Phase 1:
> ```bash
> python -m cli parse books/your-textbook.pdf --slug MYBOOK
> ```

This also works with the `all` command:

```bash
python -m cli all books/textbook.pdf --slug MYBOOK --verbose-mode
```

### Phase 3 (Optional): Quality Review / 质量审核

```bash
python -m cli review MYBOOK                     # Review all chapters
python -m cli review MYBOOK --chapters 1 2 3    # Specific chapters
```

Report saved to `data/MYBOOK/review_report.json`.

### Phase 4: Package as MkDocs Site / 打包网站

```bash
python -m cli package MYBOOK
python -m cli package MYBOOK --site-name "Display Name"

cd output/MYBOOK && mkdocs serve   # Preview at http://127.0.0.1:8000
```

Add `-v` to any command for debug logging.

## Requirements

- Python >= 3.12

依赖通过 `pyproject.toml` 管理，按需安装：

```bash
pip install -e .            # 默认（解析 + LLM 生成）
pip install -e ".[ocr]"     # + OCR 增强 PDF 解析
pip install -e ".[site]"    # + MkDocs 站点打包
pip install -e ".[dev]"     # + 开发测试
pip install -e ".[all]"     # 全部
```
