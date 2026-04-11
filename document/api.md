# Usage / 使用指南

## Installation

```bash
git clone https://github.com/charliechen114514/grimoire.git
cd grimoire
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### API Key Configuration / API 密钥配置

Create a `.env` file in the project root:

```bash
ANTHROPIC_API_KEY=your-api-key-here
ANTHROPIC_BASE_URL=https://optional-proxy.example.com/api/anthropic
```

- `ANTHROPIC_API_KEY` — Required. Your Anthropic API key.
- `ANTHROPIC_BASE_URL` — Optional. Proxy endpoint (e.g., `https://open.bigmodel.cn/api/anthropic`). Defaults to Anthropic's official API.

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

- Python 3.12（PS: 3.14 Might Sucks In Pillow Compile）
- `anthropic >= 0.40.0`
- `pymupdf >= 1.24.0`
- `pydantic >= 2.0.0`
- `mkdocs >= 1.6.0` + `mkdocs-material >= 9.5.0`
- `python-dotenv >= 1.0.0`
