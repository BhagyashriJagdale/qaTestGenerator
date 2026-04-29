# QA Test Case Generator

An AI-powered, multi-agent system that transforms plain requirements into production-grade test cases — manual, API automation, and UI automation — with built-in quality enforcement and a self-improving feedback loop.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [LLM Providers](#llm-providers)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI](#cli)
  - [Python API](#python-api)
  - [REST API Server](#rest-api-server)
- [Pipeline Deep Dive](#pipeline-deep-dive)
- [Quality Enforcement](#quality-enforcement)
- [Output Format](#output-format)
- [Project Structure](#project-structure)
- [Adding Domain Knowledge](#adding-domain-knowledge)

---

## Features

- **Multi-Agent Pipeline** — four specialised agents (Planner → Generator → Reviewer → Formatter) with a self-improving feedback loop
- **Multiple Input Formats** — plain text descriptions, Acceptance Criteria, User Stories (auto-detected)
- **Three Output Types** — manual step-by-step tests, Playwright TypeScript API scripts, Playwright TypeScript UI scripts
- **Guaranteed Negative Coverage** — negative scenarios are enforced at both prompt and post-processing levels; synthesised automatically if the LLM omits them
- **Mandatory Preconditions** — every manual test case always has preconditions describing auth state, data state, and environment
- **Detailed Steps & Assertions** — steps name exact elements and supply concrete test data; automation scripts assert status codes AND body fields
- **Feedback Loop** — Reviewer output (gaps, issues, suggestions) is fed back to the Planner, which refines its analysis; the loop runs up to 3 times and keeps the best-scoring result
- **Retry Logic** — Generator retries up to 3 times with escalating temperature when the LLM returns zero test cases
- **RAG Integration** — ChromaDB knowledge base learns from past test cases for consistent patterns
- **REST API** — FastAPI server for programmatic integration
- **CLI** — command-line tool with interactive and inline input modes

---

## Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │                  FEEDBACK LOOP (up to 3x)            │
                        │                                                       │
  Requirement ──▶  Planner Agent  ──▶  Generator Agent  ──▶  Reviewer Agent   │
                      ▲    │                  │                     │           │
                      │    ▼                  ▼                     │           │
                      │  Analysis        Test Cases            Review Result    │
                      │                (manual + API + UI)    (score + gaps)   │
                      │                                             │           │
                      └─────────────── refine() ◀──────────────────┘           │
                        (if score < 75% and iterations remain)                 │
                        └─────────────────────────────────────────────────────┘
                                               │
                                               ▼ best result
                                        Formatter Agent
                                               │
                                               ▼
                                      Markdown Documentation
                                               │
                                               ▼
                                    RAG Knowledge Base (ChromaDB)
```

### Agents

| Agent | Role |
|---|---|
| **Planner** | Analyses the requirement — extracts feature name, domain, endpoints, UI elements, test focus areas. On feedback iterations, refines the analysis using Reviewer gaps and suggestions. |
| **Generator** | Produces manual tests, API scripts, and UI scripts. Retries up to 3× if output is empty. Post-processing guards enforce preconditions, negative scenarios, and assertion quality. |
| **Reviewer** | Scores the output across coverage, clarity, automation quality, and best practices. Returns gaps, issues, and improvement suggestions that feed back to the Planner. |
| **Formatter** | Renders everything into a clean, professional Markdown document. |

---

## LLM Providers

Set `LLM_PROVIDER` in `.env` to select the backend:

| Provider | Value | Key variable |
|---|---|---|
| OpenAI (GPT-4o, etc.) | `openai` | `OPENAI_API_KEY` |
| Anthropic (Claude) | `anthropic` | `ANTHROPIC_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| HuggingFace (local) | `huggingface` | _(none — model loaded locally)_ |

---

## Installation

```bash
# 1. Enter the project directory
cd qa-test-generator

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set your LLM_PROVIDER and the matching API key
```

---

## Configuration

All configuration lives in `.env`:

```bash
# ── LLM Provider ──────────────────────────────────────────────────────────────
LLM_PROVIDER=deepseek           # openai | anthropic | deepseek | huggingface
MODEL_NAME=deepseek-chat        # model identifier for the chosen provider
MAX_TOKENS=4096

# ── API Keys (set only the one matching LLM_PROVIDER) ─────────────────────────
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...

# ── RAG (ChromaDB) ────────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR=./data/chroma
EMBEDDING_MODEL=all-MiniLM-L6-v2

# ── API Server ────────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false

# ── Jira Integration (optional) ───────────────────────────────────────────────
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your_email@company.com
JIRA_API_TOKEN=your_jira_token
```

---

## Usage

### CLI

#### Interactive mode (type or paste a description)

```bash
python main.py generate
```

You will be prompted to enter your requirement. Press **Enter on a blank line** to finish.
Accepts all three formats — plain text, user story, or acceptance criteria.

#### Inline description

```bash
# Plain text
python main.py generate "Users can add products to their shopping cart"

# User story
python main.py generate \
  "As a shopper I want to add products to my cart so that I can purchase them later" \
  -t user_story

# Acceptance criteria from a file
python main.py generate -f requirements.txt -t acceptance_criteria -o tests.md
```

#### Common flags

| Flag | Description |
|---|---|
| `-f FILE` | Read requirement from a file |
| `-o FILE` | Save markdown output to a file |
| `-t TYPE` | Input type: `plain_text` (default), `acceptance_criteria`, `user_story` |
| `-c TEXT` | Project context (e.g. "E-commerce platform") |
| `--tech TEXT` | Technology stack (e.g. "React, Node.js, PostgreSQL") |
| `--no-manual` | Skip manual test cases |
| `--no-api` | Skip API automation scripts |
| `--no-ui` | Skip UI automation scripts |
| `--no-rag` | Disable RAG context retrieval |

#### Examples

```bash
# Generate API tests only, save to file
python main.py generate "Cart API endpoints" --no-manual --no-ui -o cart_api_tests.md

# Provide project context and tech stack
python main.py generate -f story.txt \
  -c "Mobile e-commerce app" \
  --tech "React Native, FastAPI, PostgreSQL"

# RAG stats and knowledge management
python main.py rag-stats
python main.py add-knowledge "Always test with expired JWT tokens" \
  -d authentication -t best_practice
```

---

### Python API

```python
from pipeline import generate_test_cases

result = generate_test_cases(
    requirement_text="User can login with email and password",
    input_type="plain_text",          # plain_text | acceptance_criteria | user_story
    project_context="E-commerce app",
    tech_stack="React, Node.js, PostgreSQL",
    use_rag=True,
)

print(result.markdown_output)                   # full formatted documentation
print(f"Total tests:   {len(result.manual_test_cases) + len(result.api_test_cases) + len(result.ui_test_cases)}")
print(f"Quality score: {result.review.final_score}%")
print(f"Coverage gaps: {result.review.coverage.coverage_gaps}")
```

---

### REST API Server

```bash
python main.py server --port 8000
# or
uvicorn api.server:app --reload
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/generate` | Synchronous generation |
| `POST` | `/generate/async` | Async generation (returns job ID) |
| `GET` | `/jobs/{job_id}` | Poll job status and result |
| `POST` | `/knowledge/add` | Add domain knowledge to RAG |
| `GET` | `/health` | Health check |

Interactive docs: `http://localhost:8000/docs`

---

## Pipeline Deep Dive

### Feedback Loop

The pipeline runs up to **3 iterations** automatically:

1. **Planner** analyses the requirement and produces a structured analysis.
2. **Generator** creates manual tests, API scripts, and UI scripts.
3. **Reviewer** scores the output (0–100) and identifies gaps, issues, and suggestions.
4. If the score is **≥ 75%** → stop, use this result.
5. If iterations remain → the Reviewer's feedback (gaps, issues, suggestions) is passed to the **Planner**, which produces a refined analysis targeting the missed areas.
6. Repeat from step 2 with the refined analysis.
7. The **best-scoring result** across all iterations is sent to the Formatter.

### Generator Retry Logic

Within each pipeline iteration, the Generator retries up to **3 times** with escalating temperature (`0.5 → 0.6 → 0.7`) if the LLM returns zero test cases.

### Quality Guards (post-processing)

Even when the LLM follows all instructions, the following guards run on every output:

| Guard | What it does |
|---|---|
| `_ensure_preconditions()` | Fills empty `preconditions` arrays with scenario-appropriate defaults (auth state, data state, environment) |
| `_ensure_negative_manual_scenarios()` | If no negative manual tests exist, synthesises two: invalid input rejected + unauthorised access blocked |
| `_ensure_negative_automation_scenarios()` | If no negative API or UI tests exist, synthesises a complete runnable Playwright TypeScript script covering 401, 400, and 404 (API) or form validation + auth guard + invalid input (UI) |

---

## Quality Enforcement

### Manual Tests

- Every test case **must** have at least one precondition
- At least **2 negative scenarios** required (invalid input + unauthorised access)
- Steps must name **exact UI elements or endpoints** and supply **concrete test data**
- Expected results must be **specific and measurable** — vague phrases like "works correctly" are rejected

### API Automation

- Every `test()` block **must** assert `response.status()` AND at least one field from the response body
- Mandatory negative tests: `401/403` (no auth), `400` (bad body), `404` (unknown ID)
- Assertions use `toMatchObject`, `toEqual`, `toContain` — `toBeTruthy()` alone is prohibited

### UI Automation

- Page Object Model is mandatory — a typed page object class defined before `test.describe`
- Every `test()` block must include at least one Playwright async assertion (`toBeVisible`, `toHaveText`, `toHaveURL`, `toHaveValue`)
- No `setTimeout` or `sleep` — Playwright's built-in waiting only
- Locators: `data-testid > role > label > placeholder > id > CSS`

---

## Output Format

The Formatter produces a Markdown document with:

```
# Test Cases: [Feature Name]
Generated: [Date] | Quality Score: [Score]%

## Summary
Total / Manual / API Automation / UI Automation counts
Scenario coverage matrix

## 1. Manual Test Cases
TC-001 | Priority | Scenario Type
  Preconditions
  Steps table (Action → Expected Result)
  Postconditions

## 2. API Automation Test Scripts
tests/api/[feature].api.spec.ts
  Full TypeScript code

## 3. UI Automation Test Scripts
tests/ui/[feature].ui.spec.ts
  Full TypeScript code

## Coverage Report
## Notes & Recommendations
```

---

## Project Structure

```
qa-test-generator/
├── agents/
│   ├── base_agent.py          # Shared LLM call logic
│   ├── planner_agent.py       # Requirement analysis + refinement
│   ├── generator_agent.py     # Test case generation + quality guards
│   ├── review_agent.py        # Scoring and feedback
│   ├── formatter_agent.py     # Markdown formatting
│   └── prompts.py             # All system prompts
├── api/
│   └── server.py              # FastAPI REST server
├── config/
│   └── settings.py            # Pydantic settings (loaded from .env)
├── core/
│   ├── models.py              # Pydantic data models
│   ├── llm_client.py          # OpenAI / Anthropic / DeepSeek / HuggingFace clients
│   ├── supabase_db.py         # Supabase persistence (optional)
│   └── github_db.py           # GitHub Gist persistence (optional)
├── rag/
│   └── rag_system.py          # ChromaDB RAG integration
├── tools/                     # External integrations (Jira, API docs)
├── templates/                 # Output templates
├── tests/                     # Unit tests
├── main.py                    # CLI entry point
├── pipeline.py                # Main orchestrator (feedback loop)
├── requirements.txt
├── .env.example
└── supabase_schema.sql
```

---

## Adding Domain Knowledge

Teach the RAG system domain-specific patterns to improve future generation quality:

```bash
# Via CLI
python main.py add-knowledge \
  "Always test OAuth token refresh — use an expired token and verify a 401 triggers a refresh" \
  -d authentication -t best_practice

python main.py add-knowledge \
  "Cart quantity must be validated server-side; client-side checks alone are insufficient" \
  -d ecommerce -t requirement

# Via REST API
curl -X POST http://localhost:8000/knowledge/add \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Payment flows must test declined cards, insufficient funds, and network timeouts",
    "domain": "payments",
    "knowledge_type": "best_practice"
  }'
```

---

## License

MIT License
