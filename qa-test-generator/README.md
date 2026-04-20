# QA Test Case Generator

AI-powered test case generation system that transforms requirements into production-grade test cases.

## Features

- **Multi-Agent Pipeline**: 4 specialized agents (Planner → Generator → Review → Formatter)
- **Multiple Input Formats**: Plain text, Acceptance Criteria, User Stories
- **Multiple Output Types**: Manual test cases, API automation (Playwright), UI automation (Playwright)
- **Comprehensive Coverage**: Happy path, negative, edge cases, boundary, security scenarios
- **RAG Integration**: Learns from past test cases for consistent patterns
- **REST API**: FastAPI server for integration
- **CLI Tool**: Command-line interface for quick generation

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Planner Agent  │───▶│ Generator Agent │───▶│  Review Agent   │───▶│ Formatter Agent │
│                 │    │                 │    │                 │    │                 │
│ Analyzes reqs   │    │ Creates tests   │    │ Reviews quality │    │ Formats output  │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │                                              │
         │                      │                                              │
         ▼                      ▼                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              RAG Knowledge Base (ChromaDB)                          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone and enter directory
cd qa-test-generator

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY
```

## Quick Start

### CLI Usage

```bash
# Generate from inline requirement
python main.py generate "User can login with email and password"

# Generate from file
python main.py generate -f requirements.txt -o tests.md

# Generate only API tests
python main.py generate "Login API" --no-manual --no-ui

# Specify input type
python main.py generate -t user_story "As a user, I want to reset my password"
```

### API Server

```bash
# Start server
python main.py server --port 8000

# Or directly
uvicorn api.server:app --reload
```

Then access:
- Swagger UI: http://localhost:8000/docs
- API endpoints:
  - `POST /generate` - Synchronous generation
  - `POST /generate/async` - Async with job polling
  - `GET /jobs/{job_id}` - Check job status
  - `GET /health` - Health check

### Python API

```python
from pipeline import generate_test_cases

result = generate_test_cases(
    requirement_text="User can login with email and password",
    input_type="plain_text",
    project_context="E-commerce platform",
    tech_stack="React, Node.js, PostgreSQL"
)

# Access outputs
print(result.markdown_output)  # Formatted documentation
print(f"Total tests: {len(result.manual_test_cases)}")
print(f"Quality score: {result.review.final_score}%")
```

## Configuration

Environment variables (`.env`):

```bash
# Required
ANTHROPIC_API_KEY=your_key_here

# Optional
MODEL_NAME=claude-sonnet-4-20250514
MAX_TOKENS=4096
CHROMA_PERSIST_DIR=./data/chroma
API_PORT=8000
```

## Output Example

The system generates:

### Manual Test Cases
- Step-by-step instructions
- Preconditions and postconditions
- Expected results
- Priority and tags

### API Automation (Playwright TypeScript)
```typescript
test.describe('Login API', () => {
  test('should login with valid credentials', async ({ request }) => {
    const response = await request.post('/api/auth/login', {
      data: { email: 'user@example.com', password: 'password123' }
    });
    expect(response.ok()).toBeTruthy();
  });
});
```

### UI Automation (Playwright TypeScript)
```typescript
test.describe('Login Page', () => {
  test('should login successfully', async ({ page }) => {
    await page.goto('/login');
    await page.fill('[data-testid="email"]', 'user@example.com');
    await page.fill('[data-testid="password"]', 'password123');
    await page.click('[data-testid="submit"]');
    await expect(page).toHaveURL('/dashboard');
  });
});
```

## Project Structure

```
qa-test-generator/
├── agents/              # AI agents
│   ├── planner_agent.py
│   ├── generator_agent.py
│   ├── review_agent.py
│   └── formatter_agent.py
├── api/                 # FastAPI server
│   └── server.py
├── config/              # Configuration
│   └── settings.py
├── core/                # Core models and LLM client
│   ├── models.py
│   └── llm_client.py
├── rag/                 # RAG system
│   └── rag_system.py
├── tools/               # External integrations (Jira, etc.)
├── tests/               # Unit tests
├── main.py              # CLI entry point
├── pipeline.py          # Main orchestrator
└── requirements.txt
```

## Adding Domain Knowledge

Improve test quality by adding domain-specific knowledge:

```bash
# Via CLI
python main.py add-knowledge "Always test OAuth tokens with expired/invalid values" \
  -d authentication -t best_practice

# Via API
curl -X POST http://localhost:8000/knowledge/add \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "domain": "authentication", "knowledge_type": "best_practice"}'
```

## License

MIT License
