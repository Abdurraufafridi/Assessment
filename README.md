# Proposal Research Agent

RAG-powered, multi-agent system that turns client discovery transcripts into
tailored, source-grounded proposal documents.

The core ingestion, retrieval, agent, workflow-state, and DOCX rendering layers
are implemented and tested. The Slack-facing layer, follow-up revision loop, and
human approval step are unfinished. See [DECISION.md](DECISION.md) for what was
built, what was left out, and why.

Built incrementally by phase. This repository contains **Phase 0: Foundation**,
**Phase 1: RAG Ingestion Pipeline**, **Phase 2: Database Schema and Application
State**, **Phase 3: AI Intake Agent**, **Phase 4: Research, Planning, and Writing
Agents**, and **Phase 5: DOCX Document Renderer**.

## Submission status

- [x] Source code and seed data
- [x] Local setup and run instructions
- [x] Architecture and decision document ([DECISION.md](DECISION.md))
- [x] Automated tests, linting, and type checking
- [ ] Slack upload/file-delivery flow and follow-up revisions
- [ ] 3–5 minute demo video (depends on the unfinished Slack flow)

The required Slack demo video was not recorded because that part of the system
was left unfinished due to time. The local pipeline below can be used to exercise
the implemented agents and DOCX renderer.

## Requirements

- Python 3.11 or 3.12 recommended (PyTorch has no Intel-macOS wheel for 3.13)
- A Google Gemini API key, an OpenRouter API key, or a local Ollama instance
- Internet access on first embedding run to download the sentence-transformers model
- Slack credentials are reserved for the unfinished Slack adapter and are not
  required to run the current system

## Phase status

Phase 0 (foundation):

- Environment-based configuration with secret masking
- Structured console/JSON logging
- SQLAlchemy 2.0 database layer (SQLite now, PostgreSQL-compatible URL)
- FastAPI application factory and liveness/readiness endpoints

Phase 1 (RAG ingestion):

- TXT, Markdown, PDF, and DOCX text extraction
- Unicode/whitespace cleaning with paragraph preservation
- Configurable, boundary-aware overlapping chunking
- Local sentence-transformers embeddings (`all-MiniLM-L6-v2` by default in `.env.example`)
- Persistent ChromaDB storage with industry, proposal-type, source, and document-ID metadata
- SHA-256 duplicate detection and completed/failed ingestion tracking in SQLite
- Structured ingestion logs and recoverable failure handling

Phase 2 (database schema and application state):

- Users, documents, workflows, tasks, agent executions, and workflow-document links
- Foreign keys, cascade/delete rules, check constraints, unique constraints, and query indexes
- Alembic migrations with a metadata-parity test against the ORM models
- Repository layer for every aggregate plus application services for state and references
- Versioned workflow-state JSON with optimistic concurrency checks
- State schemas for stages, statuses, task/document references, revision counts, and errors
- Reference validation ensures documents and tasks belong to the workflow/user that uses them

Phase 3 (AI intake agent):

- Gemini, OpenRouter, and Ollama JSON-generation adapters behind a provider-neutral interface
- Strict intake system prompt focused only on requirement understanding
- Structured `IntakeResult` with objective, deliverable type, audience, required inputs,
  constraints, missing information, clarification questions, status, and confidence
- Pydantic validation rejects malformed JSON, unknown fields, invalid enums, and
  inconsistent ready/clarification states
- Normalized requests and prior intake results support follow-up clarification answers
- Validated intake is saved to the workflow state JSON and `extracted_requirements`
- Ready intake moves the workflow to `running`; clarification needs move it to `awaiting_input`

Phase 4 (research, planning, and writing agents):

- Research agent retrieves chunks from the RAG store, validates citation-backed
  findings, and preserves source names, document IDs, chunk IDs, scores, excerpts,
  and chunk metadata
- Planning agent converts research into an ordered, evidence-backed outline and
  flags missing evidence
- Writing agent produces grounded sections from approved research and an approved
  outline, with deterministic source references and citation validation
- Structured `ResearchResult`, `PlanningResult`, and `WritingResult` objects are
  persisted in the shared workflow state as `research`, `outline`, and `draft`
- Writing refuses insufficient research or outlines that still need evidence, and
  rejects unknown, numeric, unapproved, or undeclared citations
- `ProposalPipeline` runs the three agents sequentially within the existing
  `research -> writing` workflow stages

Phase 5 (DOCX document renderer):

- Converts shared-state `WritingResult` output into a formatted DOCX, or renders
  explicit `DocumentContent` blocks
- Supports headings, paragraphs, bullet lists, tables, captions, and page breaks
- Adds a title page, headers, footers, and `PAGE`/`NUMPAGES` fields where configured
- Preserves inline citation markers and emits a deterministic source-reference section
- Includes built-in `professional` and `minimal` templates plus configurable
  programmatic styling and base `.docx` templates
- Saves files atomically under `DOCUMENT_STORAGE_DIR` and returns path, content hash,
  byte size, template name, counts, timestamps, and metadata

Left unfinished because of the short time available: the Slack bot and file
delivery, follow-up Q&A and section-level revision, human approval checkpoints,
cross-session Slack conversation memory, and workflow/document API routes. The
database and versioned state model needed to support those features are in place.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

Edit `.env` and set `LLM_PROVIDER` plus the matching credentials and model name:

- Gemini: `GEMINI_API_KEY` and `GEMINI_MODEL`
- OpenRouter: `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`
- Ollama: `OLLAMA_MODEL` and, if needed, `OLLAMA_BASE_URL`

`DATABASE_URL`, `CHROMA_PERSIST_DIRECTORY`, and `DOCUMENT_STORAGE_DIR` control
local storage. See [.env.example](.env.example) for every supported setting.
API keys are never required in source control; `.env` is ignored.

Production deployments should run `alembic upgrade head` before starting the
application. Development and test environments still use `create_all` as a
convenience; a test compares the migrations and ORM metadata to keep them
aligned.

The embedding stack is pinned to `numpy<2`, `transformers<5`, and
`sentence-transformers<4` because Intel macOS only provides PyTorch 2.2.2.

Generated DOCX files are written to `DOCUMENT_STORAGE_DIR` (default
`./data/generated`). Select `DOCUMENT_TEMPLATE_NAME=professional` or `minimal`,
or point `DOCUMENT_TEMPLATE_PATH` at a base `.docx` template to reuse its styles,
headers, and footers.

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints:

- `GET /health` — process liveness
- `GET /health/ready` — readiness including `SELECT 1` against the database
- `GET /docs` — OpenAPI documentation

The SQLite database and its parent directory are created automatically on first
startup at the path in `DATABASE_URL`. In production, set `APP_ENV=production`
and run Alembic before starting the app; automatic schema creation is disabled
in that environment.

## Run the full local pipeline

This is the working end-to-end path without Slack: ingest the seed proposals and
transcript, run the intake agent, run research/planning/writing, and render a DOCX.

```python
from pathlib import Path

from app.agents import IntakeAgent, ProposalPipeline
from app.core.config import get_settings
from app.db.database import Database
from app.ingestion.pipeline import IngestionPipeline
from app.rendering import DocxRenderer
from app.repositories.users import UserRepository
from app.schemas.intake import IntakeStatus
from app.services.workflows import WorkflowService

settings = get_settings()
database = Database(settings.database_url)
database.create_all()

ingestion = IngestionPipeline.from_settings(database, settings)
for path in sorted(Path(".").glob("proposal_*.txt")):
    ingestion.ingest_file(path)
ingestion.ingest_file("client_transcript.txt")

with database.session() as session:
    users = UserRepository(session)
    user = users.get_by_slack_user_id("local-demo") or users.create(
        slack_user_id="local-demo",
        display_name="Local Demo",
    )
    workflow = WorkflowService(session).create_workflow(user_id=user.id)

    intake = IntakeAgent.from_settings(session=session, settings=settings).process(
        workflow_id=workflow.id,
        request=Path("client_transcript.txt").read_text(encoding="utf-8"),
    )
    if intake.status is not IntakeStatus.READY:
        raise RuntimeError(f"Intake needs clarification: {intake.clarification_questions}")

    result = ProposalPipeline.from_settings(session=session, settings=settings).run(
        workflow_id=workflow.id
    )
    rendered = DocxRenderer.from_settings(settings).render(
        result.draft,
        output_name="client-proposal.docx",
    )
    session.commit()

print(rendered.path)
```

The first embedding run downloads the configured sentence-transformers model.
The generated file is written under `DOCUMENT_STORAGE_DIR`.

## Database and state

```bash
alembic upgrade head
alembic revision --autogenerate -m "describe change"
alembic downgrade -1
```

Schema:

- `users` — Slack identity and ownership of workflows/documents
- `documents` — ingested sources and generated artifacts, including Phase 1 ingestion fields
- `workflows` — workflow aggregate plus versioned JSON state mirrored into queryable columns
- `workflow_documents` — workflow/document association with an input/reference/draft/output role
- `tasks` — ordered units of agent work linked to a workflow and optional documents
- `agent_executions` — one row per agent attempt, with payloads, token usage, latency, and errors

Workflow state updates use optimistic locking with `expected_version`. The service
validates allowed stage/status transitions, terminal-state requirements, and that
every referenced document/task belongs to the workflow. Repositories never
commit; callers own transaction boundaries. No agent reasoning or LLM calls live
in the persistence/service layer. Phase 4 results extend the versioned state JSON
with `research`, `outline`, and `draft`; an outline requires research, and a draft
requires an outline.

## Run the intake agent

Set `LLM_PROVIDER` to `gemini`, `openrouter`, or `ollama` and configure the
matching credentials/model. The intake agent only understands requirements; it
does not research or write.

- Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL` (for example `gemini-3.8-flash`).
  `gemini-3.5-flash` is deprecated and automatically routes to a newer model.
- OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (the example uses
  `nvidia/nemotron-3-ultra-550b-a55b:free`). That free model does not advertise
  `response_format`, so structured output relies on the intake prompt and the
  agent's JSON extraction/validation.
- Ollama: `OLLAMA_MODEL` and optional `OLLAMA_BASE_URL`.

```python
from app.agents import IntakeAgent
from app.core.config import get_settings
from app.db.database import Database
from app.repositories.users import UserRepository
from app.services.workflows import WorkflowService

settings = get_settings()
database = Database(settings.database_url)
database.create_all()

with database.session() as session:
    user = UserRepository(session).create(slack_user_id="U123", display_name="Ada")
    workflow = WorkflowService(session).create_workflow(user_id=user.id)
    agent = IntakeAgent.from_settings(session=session, settings=settings)
    result = agent.process(
        workflow_id=workflow.id,
        request="Create an 8-page technical proposal for Acme's warehouse modernization.",
    )
    session.commit()

print(result.model_dump_json(indent=2))
```

`IntakeResult` is defined in `app/schemas/intake.py`. Ready results persist with
workflow status `running`; requests that need more information persist the
clarification questions and move the workflow to `awaiting_input`. Pass
`previous_intake` to `analyze()` when incorporating the user's answers.

## Run research, planning, and writing

The Phase 4 agents share one workflow state. Planning happens within the existing
`research` workflow stage, so no additional database migration is required.

```python
from app.agents import ProposalPipeline
from app.core.config import get_settings
from app.db.database import Database

settings = get_settings()
database = Database(settings.database_url)

with database.session() as session:
    pipeline = ProposalPipeline.from_settings(session=session, settings=settings)
    # workflow_id must already have a ready intake result.
    result = pipeline.run(workflow_id=workflow_id)
    session.commit()

print(result.research.model_dump_json(indent=2))
print(result.outline.model_dump_json(indent=2))
print(result.draft.render_markdown())
```

Each agent can also run independently with `ResearchAgent`, `PlanningAgent`, or
`WritingAgent`. Research uses the configured collection and embedding model,
returns stable `S1`, `S2`, ... citations, and retains the original chunk metadata.
Planning only cites retrieved evidence. Writing requires `research.status ==
"sufficient"` and `outline.status == "ready"`, reproduces the approved headings in
order, and rejects unknown, numeric, unapproved, or undeclared citations. The
structured results are stored in workflow state as `research`, `outline`, and
`draft`; `research_notes` also receives a human-readable research summary.

## Render a DOCX proposal

`DocxRenderer` accepts either a validated `WritingResult` or explicit
`DocumentContent`. Text blocks use a small Markdown-like subset for rich content:
`##` through `####` sub-headings, `-` bullets, pipe tables with a separator row,
and `\f` or `<!-- pagebreak -->` page breaks.

```python
from pathlib import Path

from app.core.config import get_settings
from app.rendering import DocxRenderer
from app.schemas.document import (
    BulletListBlock,
    DocumentContent,
    DocumentSection,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
)

settings = get_settings()
renderer = DocxRenderer.from_settings(settings)

content = DocumentContent(
    title="Acme Warehouse Modernization Proposal",
    subtitle="Technical response",
    prepared_for="Acme Operations",
    prepared_by="Proposal Team",
    sections=[
        DocumentSection(
            heading="Client Needs",
            blocks=[
                ParagraphBlock(text="Inventory visibility is the primary need [S1]."),
                BulletListBlock(items=["Real-time visibility", "Phased rollout"]),
                TableBlock(
                    headers=["Phase", "Timing"],
                    rows=[["Discovery", "Q1"], ["Rollout", "Q2"]],
                ),
                PageBreakBlock(),
            ],
        )
    ],
)
result = renderer.render(content, output_name="acme-proposal.docx")

print(result.path)
print(result.content_hash, result.byte_size)
print(result.metadata)
```

For `WritingResult` input, use `renderer.render(writing_result)`. The renderer
parses paragraph, bullet, table, sub-heading, and page-break markers from section
content, preserves inline citations, and appends the cited sources.

Routes do not expose rendering yet; this phase provides the reusable service API,
filesystem storage, template selection, and metadata contract.

## Ingest documents

```python
from app.core.config import get_settings
from app.db.database import Database
from app.ingestion.pipeline import IngestionPipeline

settings = get_settings()
database = Database(settings.database_url)
database.create_all()

pipeline = IngestionPipeline.from_settings(database, settings)
result = pipeline.ingest_file(
    "proposal_logistics.txt",
    metadata={"industry": "logistics", "proposal_type": "past_proposal"},
)
print(result.document_id, result.status, result.chunk_count)
```

Re-ingesting identical bytes returns `duplicate` without re-embedding. Pass
`force=True` to replace an existing index. Supported extensions are `.txt`,
`.md`, `.markdown`, `.pdf`, and `.docx`.

Metadata inferred automatically: `document_type`, `proposal_type`, and
`industry` for filenames following `proposal_<industry>.txt`; callers may
override or extend metadata. Each chunk also stores `document_id`,
`source_name`, `source_type`, `content_hash`, `chunk_index`, and `chunk_count`.

## Test and check

```bash
pytest
ruff check .
ruff format --check .
mypy app

# Opt in to the real embedding-model and semantic-retrieval test
RUN_EMBEDDING_TESTS=1 pytest tests/integration/test_embeddings_and_retrieval.py
```

Tests use temporary SQLite/Chroma directories and cover CRUD, relationships,
constraints, migrations, service validation, workflow-state updates, intake
normal/incomplete/ambiguous requests, invalid LLM output handling, RAG retrieval,
research provenance, planning gaps, citation-safe writing, the end-to-end Phase 4
pipeline, and DOCX generation, formatting, tables, special characters, templates,
storage, and empty sections. The keyword embedder and agent LLM doubles in tests
are explicit test doubles; production uses sentence-transformers and a configured
Gemini/OpenRouter/Ollama provider.

## Project structure

```
DECISION.md                  architecture, trade-offs, and unfinished work
.github/workflows/ci.yml     GitHub Actions lint, type-check, and test workflow
app/
  agents/intake.py           intake prompt, JSON parsing, validation, state save
  agents/research.py         RAG retrieval, evidence validation, provenance
  agents/planning.py         evidence-backed outline and missing-evidence detection
  agents/writing.py          grounded writing and citation enforcement
  agents/pipeline.py         sequential research -> planning -> writing runner
  agents/structured.py       shared structured-output parsing
  api/routes/health.py       health endpoints
  core/config.py             environment configuration
  core/logging.py            structured logging
  db/base.py                 SQLAlchemy base + naming conventions
  db/database.py             engine/session factory, SQLite foreign keys
  db/models/                 users, documents, workflows, tasks, executions, links
  domain/                    state enums, transition rules, domain errors
  llm/                       Gemini/OpenRouter/Ollama adapters and factory
  repositories/              data access for every aggregate
  schemas/intake.py          validated intake result contract
  schemas/research.py        findings, evidence, and source-reference contracts
  schemas/planning.py        ordered outline and missing-evidence contract
  schemas/writing.py         grounded draft and citation contract
  schemas/document.py        renderable blocks and rendered-document result contract
  schemas/workflow.py        validated workflow state and update schemas
  rendering/docx.py          professional DOCX generation and atomic storage
  rendering/parser.py        Markdown-like text to document-block conversion
  rendering/template.py      built-in and base-DOCX template configuration
  services/                  state/reference rules and transaction-neutral orchestration
  services/retrieval.py      RAG query embedding and vector-store retrieval
  ingestion/loaders.py       TXT/MD/PDF/DOCX extraction
  ingestion/cleaning.py      text normalisation
  ingestion/chunking.py      configurable overlapping chunks
  ingestion/metadata.py      metadata inference/filter-safe values
  ingestion/pipeline.py      end-to-end ingestion orchestration
  embeddings/                provider interface + sentence-transformers provider
  vectorstore/               provider interface + persistent Chroma implementation
  main.py                    FastAPI application factory
migrations/                  Alembic environment and versioned schema migrations
tests/
  unit/                      config, loaders, chunking, CRUD, services, agents, retrieval
  integration/               HTTP endpoints, ingestion, migrations, semantic retrieval, Phase 4
```
