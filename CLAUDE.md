# CLAUDE.md — Tutorial Summon 项目指南

## 虚拟环境（强制）

**所有 Python 命令必须通过 `.venv` 虚拟环境执行，不得使用系统 Python。**

- 激活虚拟环境：`source .venv/bin/activate`
- 运行脚本：`.venv/bin/python <script>` 或激活后 `python <script>`
- 安装依赖：`pip install -e ".[dev]"`（开发模式）
- 运行测试：`pytest`
- 如虚拟环境不存在，先创建：`python3 -m venv .venv && source .venv/bin/activate && pip install -e .`

## 项目概览

Tutorial Summon 是一个 PDF/网页教材 → 交互式教程的 AI 生成管线。

- **CLI 入口**：[cli.py](cli.py)，通过 `summon` 命令或 `python cli.py` 调用
- **核心源码**：[src/](src/) — 解析、LLM Agent、编排、打包
- **Python 版本**：>= 3.12
- **包管理**：`pyproject.toml`，无 requirements.txt
- **LLM 后端**：Anthropic Claude API（通过 `anthropic` SDK）
- **可选依赖组**：`[web]` `[ocr]` `[site]` `[dev]` `[all]`

## 常用命令

```bash
source .venv/bin/activate

# 解析 PDF 为章节
python cli.py parse books/book.pdf --slug MYBOOK

# 解析 Wolai 页面（自动检测引擎）
python cli.py parse https://www.wolai.com/xxx --slug MYBOOK

# 指定 Web 引擎
python cli.py parse https://example.com --slug MYBOOK --engine static
python cli.py parse https://spa.example.com --slug MYBOOK --engine playwright

# 批量生成教程
python cli.py batch MYBOOK --workers 4

# 审查质量
python cli.py review MYBOOK

# 审查并自动修复未通过章节
python cli.py review MYBOOK --fix --max-retries 2

# 打包为 MkDocs 站点
python cli.py package MYBOOK --site-name "My Book"

# 全流程（默认含 review + auto-fix）
python cli.py all books/book.pdf --slug MYBOOK --workers 4

# 全流程（跳过 auto-fix）
python cli.py all books/book.pdf --slug MYBOOK --workers 4 --no-fix
```

## 项目结构

```
cli.py               # CLI 入口 & 子命令分发
src/
  config.py          # 全局配置（路径、模型、token 预算）
  log.py             # loguru 日志设置
  batch.py           # 批量并行处理
  review.py          # 教程质量审查 + auto-fix 工作流
  packager.py        # MkDocs 打包
  orchestrator.py    # 单章编排
  section_splitter.py# 章节分割
  glossary.py        # 术语表生成
  schema.py          # Pydantic 数据模型
  progress.py        # 批处理进度追踪（断点续跑）
  agents/            # LLM Agent（base_agent、tldr、concept、exercise、writing、review、fix）
  parsers/           # 输入解析器
    base.py          # BaseParser 抽象基类
    pdf_parser.py    # PDF 解析器
    pdf_images.py    # PDF 图片提取
    __init__.py      # get_parser() 工厂 + 引擎路由
    engines/         # Web 解析引擎（插件式）
      base.py        # BaseWebEngine 抽象基类
      wolai.py       # Wolai API 引擎（公开 API，秒级解析）
      static.py      # httpx + BeautifulSoup 静态 HTML 引擎
      playwright.py  # Playwright SPA 渲染引擎
      __init__.py    # 引擎自动发现与注册
config/              # 写作风格等配置文件
prompts/             # Prompt 模板
document/            # 架构文档与使用指南
tests/               # 测试
output/              # 生成的教程 Markdown
data/                # 中间数据（chapters_raw.json 等）
books/               # 原始 PDF 文件
```

## Web 解析引擎系统

Web 解析采用插件式引擎架构，每种 Web 来源对应一个独立的 Python 引擎文件。

### 内置引擎

| 引擎 | 名称 | 说明 | 速度 |
|------|------|------|------|
| Wolai | `wolai` | 通过 Wolai 公开 API 直接获取，自动检测域名 | 极快（~7s/27章） |
| Static | `static` | httpx + BeautifulSoup，传统服务端渲染网站 | 快 |
| Playwright | `playwright` | 浏览器渲染 SPA 页面（Wolai/Notion 等通用） | 慢 |

### 引擎选择逻辑

1. `--engine name` 显式指定 → 使用指定引擎
2. URL 域名自动匹配 → 如 `wolai.com` 自动走 Wolai 引擎
3. 无匹配 → 默认回退到 `static` 引擎

### 自定义引擎

用户只需创建一个 `.py` 文件，继承 `BaseWebEngine`：

```python
from src.parsers.engines.base import BaseWebEngine
from src.schema import ChaptersRaw

class MyEngine(BaseWebEngine):
    NAME = "myengine"
    DOMAINS = ["example.com"]

    def parse(self, source: str, book_slug: str) -> ChaptersRaw:
        # 实现解析逻辑
        ...

# 必须暴露 engine 类变量
engine = MyEngine
```

使用：`summon parse https://example.com/page --slug MY --engine ./my_engine.py`

### 新增引擎开发步骤

1. 在 `src/parsers/engines/` 下创建 `.py` 文件
2. 继承 `BaseWebEngine`，设置 `NAME` 和 `DOMAINS`
3. 实现 `parse()` 方法，返回 `ChaptersRaw`
4. 引擎会被自动发现和注册，无需手动配置

## 编码规范

- 使用 `loguru` 进行日志记录，不使用标准 `logging`
- 配置通过 `src/config.py` 集中管理，环境变量用 `python-dotenv` 加载
- 数据模型用 Pydantic v2
- 类型注解：使用 Python 3.12+ 语法（`str | None` 而非 `Optional[str]`）
