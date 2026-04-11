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
| **WritingAgent** | Generates tutorial body in the configured persona style (default: Chinese "engineer blogger"). Supports **verbose mode** for section-by-section faithful rewriting. |
| **ExerciseAgent** | Produces 3-5 leveled exercises (understanding / application / thinking) with answers |
| **TLDRAgent** | Distills the tutorial into up to 5 key takeaways |
| **ReviewAgent** | Evaluates each chapter on style, difficulty curve, and concept density (1-10, pass >= 7) |

## Verbose Mode

Verbose mode (`--verbose-mode`) is an alternative generation strategy that produces detailed, faithful rewrites instead of condensed summaries.

### Motivation

In standard mode, each chapter is processed by a single LLM call with an 8K token output limit. For chapters with 100K+ characters of source material, this results in heavy compression (~20% content retention). Verbose mode solves this by splitting chapters into manageable sections and rewriting each separately.

### How it works

1. **Adaptive section splitting** (`src/section_splitter.py`):
   - Uses PDF TOC metadata to split chapters by L2 headings
   - Sections exceeding `VERBOSE_TARGET_MAX_CHARS` (default: 30K chars) are automatically expanded into L3/L4 subsections
   - Sections shorter than `VERBOSE_MIN_SECTION_CHARS` (default: 3K chars) are merged into the previous section
   - Falls back gracefully when TOC is unavailable

2. **Per-section rewriting** (`WritingAgent.run_verbose()`):
   - Each section gets a dedicated LLM call with 16K output tokens
   - Uses specialized prompts (`writing_verbose_system.md` / `writing_verbose_user.md`) emphasizing faithful rewriting
   - **Narrative continuity**: the tail of the previous section's output is passed as context to the next section
   - First section writes the chapter introduction, last section writes the chapter summary

3. **Multi-file output**:
   - Each section is written to `ch{NN}_{S}.md` (e.g., `ch05_1.md`, `ch05_2.md`)
   - A chapter index page `ch{NN}.md` links to all sections
   - Exercises and TLDR are appended to the last section file

### Output comparison

| Metric | Standard Mode | Verbose Mode |
|---|---|---|
| Content retention | ~20% | ~75% |
| Output per chapter | ~12K chars (single file) | ~60K chars (multiple files) |
| LLM calls per chapter | 1 (WritingAgent) | N (one per section) |
| API cost | Baseline | ~3-5x |

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `VERBOSE_MAX_TOKENS` | 16384 | Max output tokens per section |
| `VERBOSE_MIN_SECTION_CHARS` | 3000 | Sections shorter than this are merged |
| `VERBOSE_TARGET_MAX_CHARS` | 30000 | Sections larger than this trigger L3 expansion |

## Project Structure

```
grimoire/
├── books/                  # Source PDF textbooks
├── config/
│   └── writing_style.md    # Persona / style guide
├── data/                   # Generated data (gitignored)
│   └── {BOOK}/
│       ├── chapters_raw.json    # Now includes TOC metadata
│       ├── global_glossary.json
│       ├── progress.json
│       └── review_report.json
├── output/                 # Tutorials & MkDocs sites (gitignored)
│   └── {BOOK}/
│       ├── tutorials/      # Raw markdown tutorials
│       │   ├── ch{NN}.md       # Chapter index (verbose) or full tutorial (standard)
│       │   └── ch{NN}_{S}.md   # Section files (verbose mode only)
│       ├── docs/           # MkDocs docs
│       └── mkdocs.yml
├── prompts/
│   ├── system/             # System prompts per agent
│   │   ├── writing_system.md
│   │   ├── writing_verbose_system.md  # Verbose mode system prompt
│   │   └── ...
│   └── user/               # User prompt templates
│       ├── writing_user.md
│       ├── writing_verbose_user.md    # Verbose mode user prompt
│       └── ...
├── cli.py                   # Unified CLI entry point
├── src/
│   ├── agents/             # AI agent implementations
│   │   ├── base_agent.py   # API client, retry, Pydantic parsing
│   │   ├── concept.py      # Supports truncate=False for verbose mode
│   │   ├── writing.py      # Includes run_verbose() method
│   │   ├── exercise.py
│   │   ├── tldr.py
│   │   └── review.py
│   ├── orchestrator.py     # Per-chapter pipeline (branching for verbose)
│   ├── section_splitter.py # Adaptive L2/L3/L4 section splitting
│   ├── batch.py            # Batch processing (passes verbose_mode + TOC)
│   ├── packager.py         # MkDocs packaging (multi-file chapter support)
│   ├── pdf_parser.py       # PDF parsing core (stores TOC in JSON)
│   ├── config.py           # Global configuration
│   └── ...
└── tests/
```

## Customization

| What | Where | Description |
|---|---|---|
| Writing persona | `config/writing_style.md` | Controls tutorial voice and tone. Also used by ReviewAgent as style reference. |
| Agent behavior | `prompts/system/*.md` | System prompts for each agent — edit without touching Python code |
| User templates | `prompts/user/*.md` | User prompt templates with variable placeholders |
| Model config | `src/config.py` | `MODEL_NAME`, `MAX_TOKENS`, `GLOSSARY_MAX_TOKENS` |
| Verbose config | `src/config.py` | `VERBOSE_MAX_TOKENS`, `VERBOSE_MIN_SECTION_CHARS`, `VERBOSE_TARGET_MAX_CHARS` |

## Limitations

- PDFs must have "Chapter N" entries in the table of contents (regex: `Chapter\s+(\d+)`).
- All prompts and the writing style guide are currently in Chinese. English support requires translating the prompts and style guide.
- Model used: `claude-sonnet-4-6-20250514`.
- Verbose mode requires re-running `parse` to embed TOC data in `chapters_raw.json` (old JSON files lack this).
- Verbose mode increases API cost ~3-5x due to multiple LLM calls per chapter.
- Some very large sections (>30K chars) without L3 sub-entries cannot be split further and are rewritten as a single block.
