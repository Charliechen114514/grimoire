# Grimoire

**[中文](#中文) | [English](#english)**

---

<a id="中文"></a>

> AI 时代了还要啃教材？把 PDF 丢进来，让它用 **你喜欢的风格** 帮你重写成带练习题的教程网站。

**[快速上手指南 →](QUICK_START.md)**

**One-liner**:

```bash
python -m cli all books/textbook.pdf --slug MYBOOK
```

Grimoire 解析技术 PDF 教材或 Web 教程网站，通过 AI 提取每章核心概念，以可配置的"工程师博主"人格生成教程正文，创建分级练习题，提炼要点，最终打包为可部署的 MkDocs 静态网站。

支持多种数据源：**PDF**、**Wolai**（公开 API 秒级解析）、**静态 HTML 网站**、**Playwright SPA 渲染**，也可通过自定义引擎插件扩展。支持 `--verbose-mode` 进行忠于原文的分节详细改写，`--workers N` 并行加速处理。

## 文档

| 文档 | 说明 |
|---|---|
| [架构设计](document/arch.md) | Pipeline 流程、Agent 说明、项目结构、自定义配置、已知限制 |
| [使用指南](document/api.md) | 安装步骤、CLI 命令、各阶段用法、依赖要求 |

## 许可证

[MIT License](LICENSE)

---

<a id="english"></a>

> Still dozing off reading PDF textbooks? Toss it in — Grimoire rewrites it into a tutorial website **in your preferred style**, complete with exercises.

**[Quick Start Guide →](QUICK_START.md)**

**One-liner**:

```bash
python -m cli all books/textbook.pdf --slug MYBOOK
```

Grimoire parses technical PDF textbooks and web tutorial sites, extracts core concepts via AI, generates tutorial content in a configurable persona, creates leveled exercises, and packages everything into a deployable MkDocs static site.

Multiple data sources supported: **PDF**, **Wolai** (public API, instant parsing), **static HTML sites**, **Playwright SPA rendering**, and custom engine plugins. Supports `--verbose-mode` for faithful section-by-section rewrites, and `--workers N` for parallel processing.

## Documentation

| Document | Description |
|---|---|
| [Architecture](document/arch.md) | Pipeline flow, agent descriptions, project structure, customization, limitations |
| [Usage](document/api.md) | Installation, CLI commands, per-phase usage, dependencies |

## License

[MIT License](LICENSE)
