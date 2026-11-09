# Decision Document

## Summary

I built the core of a multi-agent proposal system: semantic ingestion of the
seed proposals and transcript, an intake agent, a research agent with
citation-backed retrieval, a planning agent, a writing agent, persistent
workflow state, and professional DOCX rendering. The implemented flow runs from
seed data through a rendered proposal document.

The Slack-facing product flow is not finished. I left Slack upload/file delivery,
follow-up Q&A, section-level revisions, and human approval unfinished because the
assessment deadline left too little time to build and test them properly. I chose
to make the backend pipeline honest and verifiable rather than claim an
end-to-end Slack system that did not work.

## What I Built

### Multi-agent pipeline

I used four agents instead of the minimum three. Planning is separate because the
assessment explicitly forbids hardcoding the proposal structure into the writing
prompt; the planner must reason from client needs and retrieved evidence.

| Agent | Responsibility | Output |
| --- | --- | --- |
| Intake | Understand the request, constraints, and missing information; ask clarifying questions instead of guessing | Validated `IntakeResult` |
| Research | Retrieve relevant proposal/transcript chunks and turn them into supported findings | Citation-backed `ResearchResult` |
| Planning | Convert research into an ordered, evidence-backed outline | `PlanningResult` |
| Writing | Write each approved section without inventing facts or citations | `WritingResult` with `[S1]` references |

`ProposalPipeline` runs research, planning, and writing sequentially against one
shared workflow state. Research refuses non-ready intake, planning refuses
insufficient evidence, and writing refuses missing research, non-ready outlines,
or undeclared/unknown citations.

### RAG and data

- Seed ingestion supports TXT, Markdown, PDF, and DOCX.
- Text is cleaned, chunked with overlap, embedded with local
  `sentence-transformers/all-MiniLM-L6-v2`, and stored in persistent ChromaDB.
- Chunks carry `document_id`, `source_name`, `source_type`, `content_hash`,
  `chunk_index`, `chunk_count`, `industry`, `document_type`, and `proposal_type`.
- Retrieval is embedding-based, not keyword matching, with optional metadata
  filters. SHA-256 duplicate detection prevents re-embedding unchanged files.

### State and persistence

- SQLite through SQLAlchemy 2.0, with PostgreSQL-compatible models and Alembic
  migrations.
- Tables cover users, documents, workflows, workflow-document links, tasks, and
  agent executions.
- Workflow state is a versioned JSON document mirrored into queryable columns.
  Updates use optimistic concurrency and validate stage/status transitions and
  document/task ownership.
- Intake, research, outline, and draft results persist in the same workflow state,
  so a later request can resume instead of starting over.
- Generated documents are written atomically to `DOCUMENT_STORAGE_DIR`; the
  renderer returns the path, SHA-256 hash, byte size, template, counts, timestamp,
  and metadata.

### DOCX output

The renderer accepts a `WritingResult` or explicit `DocumentContent`. It supports
title pages, headings, paragraphs, bullets, tables, captions, page breaks,
headers/footers, `PAGE`/`NUMPAGES` fields, citation preservation, and a
deterministic source-reference section. Built-in `professional` and `minimal`
templates are configurable, and a base `.docx` template can be supplied.

### Quality

The code is typed, linted, and tested. Validation currently reports 121 passing
tests and one opt-in embedding test skipped by default. The suite covers database
constraints and migrations, workflow transitions, agent parsing and validation,
retrieval, citation enforcement, the research-to-writing pipeline, and DOCX
generation/formatting/storage.

## Key Decisions

| Decision | Why |
| --- | --- |
| Python 3.11 + FastAPI | Requested stack; FastAPI leaves room for the future Slack/HTTP adapter and exposes health checks now. |
| SQLite + SQLAlchemy/Alembic | Fast local setup with PostgreSQL-compatible schema and real migrations. |
| ChromaDB + sentence-transformers | Local, persistent semantic search without an extra embedding API; metadata filters are first-class. |
| Provider-neutral LLM interface | Gemini, OpenRouter, and Ollama are interchangeable through configuration; no vendor lock-in. |
| Sequential agents, no LangGraph | Easier to inspect, test, and explain under time pressure. The pipeline has explicit stage validation and one shared state. |
| Boundary-aware 1,000/150 chunking | Keeps semantic context while limiting token growth; overlap reduces boundary loss. |
| Structured Pydantic contracts | Malformed LLM output and invalid state fail before persistence instead of corrupting the workflow. |
| Citation IDs instead of free-form sources | Makes hallucinated or undeclared evidence detectable in research and writing. |

## What I Left Unfinished

I left the following parts of the project unfinished because of the short time:

1. **Slack bot and file delivery.** There is no Socket Mode/Events adapter, no
   transcript upload handling, and no DOCX upload back to Slack. The Slack
   settings are present, but unused.
2. **Follow-up Q&A and section-level revision.** The persisted draft can be
   re-rendered, but there is no revision agent that changes only the requested
   section and preserves the rest of the document.
3. **Human-in-the-loop approval.** There is no approve/reject checkpoint before
   rendering or revision.
4. **Cross-session Slack conversation memory.** The database and versioned
   workflow state support this, but there is no Slack conversation-to-workflow
   mapping or message history.
5. **Workflow/document API routes and final output registration.** Only health
   routes exist. Generated files are on disk but are not yet registered as
   workflow output documents.
6. **Demo video.** The required video depends on the unfinished Slack path, so it
   was not recorded.

I also used a generic intake contract (objective, constraints, inputs, missing
information) rather than a dedicated company/industry/budget/timeline/stakeholder
schema. That is enough to drive the pipeline, but explicit client-profile fields
would be the next improvement for more targeted retrieval.

## Next Steps

1. Add Slack Socket Mode upload/download and map Slack threads to workflow IDs.
2. Add a revision agent scoped to one section plus DOCX re-rendering and delivery.
3. Add approval states and API routes for workflow, document, and rendered output.
4. Add explicit client-profile extraction and metadata-filtered retrieval by
   industry.
5. Record the 3–5 minute end-to-end demo once the Slack path is working.
