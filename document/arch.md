# Architecture / 架构

## Pipeline

```
  PDF Textbook
      │
      ▼
  ┌──────────────────────────────────────────────────┐
  │  Phase 1: Parse  (python -m cli parse)           │
  │  pdf_parser.split_book() → chapters_raw.json     │
  └──────────────────────────────────────────────────┘
      │
      ▼
  ┌──────────────────────────────────────────────────┐
  │  Phase 2: Batch Generate  (python -m cli batch)  │
  │                                                   │
  │  Per-chapter pipeline:                            │
  │    ConceptAgent ──► WritingAgent                  │
  │         │               │                         │
  │    ExerciseAgent ◄──────┘                         │
  │         │                                         │
  │    TLDRAgent ──► merge output                     │
  │                                                   │
  │  Cross-chapter glossary accumulation              │
  └──────────────────────────────────────────────────┘
      │
      ├──── [Optional] Review: python -m cli review
      │
      ▼
  ┌──────────────────────────────────────────────────┐
  │  Phase 3: Package  (python -m cli package)       │
  │  Tutorials → MkDocs static site                  │
  └──────────────────────────────────────────────────┘
```

## Agents

| Agent | Description |
|---|---|
| **ConceptAgent** | Extracts 10-25 core concepts per chapter, tracks new vs. recurring concepts via cross-chapter glossary |
| **WritingAgent** | Generates tutorial body in the configured persona style (default: Chinese "engineer blogger") |
| **ExerciseAgent** | Produces 3-5 leveled exercises (understanding / application / thinking) with answers |
| **TLDRAgent** | Distills the tutorial into up to 5 key takeaways |
| **ReviewAgent** | Evaluates each chapter on style, difficulty curve, and concept density (1-10, pass >= 7) |

## Project Structure

```
grimoire/
├── books/                  # Source PDF textbooks
├── config/
│   └── writing_style.md    # Persona / style guide
├── data/                   # Generated data (gitignored)
│   └── {BOOK}/
│       ├── chapters_raw.json
│       ├── global_glossary.json
│       ├── progress.json
│       └── review_report.json
├── output/                 # Tutorials & MkDocs sites (gitignored)
│   └── {BOOK}/
│       ├── tutorials/      # Raw markdown tutorials
│       ├── docs/           # MkDocs docs
│       └── mkdocs.yml
├── prompts/
│   ├── system/             # System prompts per agent
│   └── user/               # User prompt templates
├── cli.py                   # Unified CLI entry point
├── src/
│   ├── agents/             # AI agent implementations
│   │   ├── base_agent.py   # API client, retry, Pydantic parsing
│   │   ├── concept.py
│   │   ├── writing.py
│   │   ├── exercise.py
│   │   ├── tldr.py
│   │   └── review.py
│   ├── orchestrator.py     # Per-chapter pipeline
│   ├── batch.py            # Batch processing
│   ├── parse.py            # PDF parsing CLI
│   ├── packager.py         # MkDocs packaging
│   ├── review.py           # Quality review
│   ├── pdf_parser.py       # PDF parsing core
│   ├── glossary.py         # Cross-chapter glossary
│   ├── progress.py         # Checkpoint / resume
│   └── config.py           # Global configuration
└── tests/
```

## Customization

| What | Where | Description |
|---|---|---|
| Writing persona | `config/writing_style.md` | Controls tutorial voice and tone. Also used by ReviewAgent as style reference. |
| Agent behavior | `prompts/system/*.md` | System prompts for each agent — edit without touching Python code |
| User templates | `prompts/user/*.md` | User prompt templates with variable placeholders |
| Model config | `src/config.py` | `MODEL_NAME`, `MAX_TOKENS`, `GLOSSARY_MAX_TOKENS` |

## Limitations

- PDFs must have "Chapter N" entries in the table of contents (regex: `Chapter\s+(\d+)`).
- All prompts and the writing style guide are currently in Chinese. English support requires translating the prompts and style guide.
- Model used: `claude-sonnet-4-6-20250514`.
