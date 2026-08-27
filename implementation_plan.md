# Credit Dossier Implementation Plan and Status

This is a living implementation record for the current architecture. It replaces the earlier OCR/direct-injection proposal, which no longer represented the main generation path.

Status labels:

- **Implemented**: present in the current backend and at least one frontend.
- **Transition**: supported, but coexists with an older path or still needs parity/hardening.
- **Planned**: recommended follow-up work; not represented as complete.

## Current delivery summary

| Area | Status | Current behavior |
|---|---|---|
| Deal workflow | Implemented | Create, edit, delete, filter, generate, submit, review, and export |
| Authentication | Implemented | PBKDF2 passwords, role-based 30/15-minute server sessions, registration/reset/change/logout |
| Authorization | Implemented | RM ownership and submission; analyst global review and approve/deny |
| Section generation | Implemented | 16 section agents, orchestration, single/selected/all generation |
| Grounding | Implemented | Company library + deal library + MCP PostgreSQL tables + section URLs |
| Guardrails | Implemented | Mistral moderation for custom instructions and templates |
| Evidence/evaluation | Implemented | Citations/retrieved sources, claim classification, confidence score |
| Narrative history | Implemented | Automatic/manual versions, mark final, compare, and delete |
| Review snapshots | Implemented | Backend and frontend support frozen submitted-version PDF download |
| Observability | Implemented | Mistral telemetry, optional Phoenix, stored metrics, observability UI |
| Local MCP | Implemented | Owner-scoped companies, 16 tables, PDF tools, caching, circuit breaker |
| Synthetic data | Implemented | Background/CLI manufacture of consistent 17-PDF and 16-table company packs |
| Exports | Implemented | PDF, DOCX, PPTX, combined report, and theme extraction |
| Legacy ingestion | Transition | OCR/direct-extraction document and section-upload endpoints retained for compatibility |

## Implemented architecture

### 1. Identity and deal access

- `User` and `AuthSession` models persist accounts and hashed session tokens.
- The backend uses one HTTP-only session cookie for the frontend.
- Relationship Managers see only owned deals and are the only role allowed to create or submit them.
- Credit Analysts can access all deals and are the only role allowed to approve or deny submitted versions.
- MCP company requests include the application user ID, preventing cross-owner company-data access.

### 2. Source model

The active generation source set is:

1. A shared, read-only company Mistral library (`company_mistral_library_id`).
2. A deal-specific Mistral library (`mistral_library_id`) for file, URL, or text sources.
3. Relevant rows selected from 16 structured MCP PostgreSQL tables.
4. Explicit per-section URLs fetched at generation time.

Library metadata and sync logs are stored in the backend database. MCP owns the company catalog and structured datasets. Company libraries are referenced rather than copied into every deal, reducing duplication.

The earlier deal-level OCR store is retained through `DealDocument` and `SectionDocumentLink`; legacy section `Upload` routes also remain. These paths should be treated as compatibility APIs, not as the description of the primary RAG flow.

### 3. Agent initialization and scoping

- Startup creates/reuses one Mistral agent per standard section and one orchestration agent.
- Section instructions are centralized in `backend/app/agents/instructions.py`.
- Orchestration prompts and section-specific deal-field selection are centralized in the orchestration modules.
- Before generation, global agents are scoped to the current deal's company and deal libraries.
- A process-level async lock protects library rebinding so concurrent users cannot attach one deal's sources to another request.
- Shutdown cleans up the global agents and disconnects MCP.

### 4. Generation pipeline

Each section follows this order:

1. Persist supplied custom instructions.
2. Moderate custom instructions and output templates. Flagged input blocks generation; moderation API failure currently fails open and records the error.
3. Fetch cached MCP document summaries and run orchestration to rank documents, priority data, search queries, and gaps.
4. Build section-specific deal context.
5. Select only the structured PostgreSQL tables relevant to that section.
6. Fetch validated section URLs and record scrape outcomes.
7. Generate through the section agent with Document Library retrieval and the assembled direct context.
8. Normalize source markers and capture retrieved-source metadata.
9. Evaluate grounded/inferred/unsupported claims and calculate confidence.
10. Save the section, observability details, narrative version, deal status, and audit entry.

Single generation uses the same pipeline as batch generation. "Draft all" fetches reusable MCP inputs once, reports job progress, and limits concurrent orchestration/generation/evaluation work with semaphores.

### 5. Accuracy and observability logic

- The claim evaluator returns grounded, inferred, and unsupported claim counts plus a summary.
- If `MISTRAL_ACCURACY_JUDGE_ID` is configured, its result supplies the displayed confidence score after normalization by `MISTRAL_ACCURACY_JUDGE_MAX_SCORE`.
- If the saved judge is missing or fails, the legacy evaluator score is used as a fallback.
- Accuracy is skipped when the deal has no library documents.
- Persisted `observability_details` contains stage status, model, latency, and token metrics where the upstream API exposes them.
- Runtime spans are emitted to Mistral telemetry with redaction and optionally to Phoenix/OpenTelemetry.

### 6. Versioning and approval logic

Section-level narrative versions and deal-level review versions have distinct lifecycles.

For narrative versions:

- Generation and manual saves create history entries.
- A user can compare versions, mark one final, or delete one.
- Deleting a version recalculates the current/final content from remaining history or the default generated content.

For deal review versions:

- An RM submission captures deal fields and ordered section content in `Version.snapshot_json` and changes the deal to `In Review`.
- An analyst approval changes the version/deal to approved; denial requires comments and returns the deal to `In Progress`.
- Download renders the immutable submitted snapshot as PDF.
- Pre-snapshot versions use the latest narrative content at or before their submission time as a compatibility fallback.

### 7. Local MCP and manufacturing

The local SSE MCP provides:

- company listing, details, documents, and summaries;
- discovery/query tools for 16 named structured credit tables;
- aggregate structured-data retrieval;
- access to 17 company PDF sources in Mistral Document Library;
- `manufacture_company_data` for consistent synthetic test packs.

Manufacturing first creates a shared borrower context, then produces 17 substantive PDFs and at least 115 rows across the 16 datasets. It is idempotent by company/generator version and has a deterministic fallback when AI generation is unavailable.

## Transition and follow-up plan

### Priority 0 - finish and protect the review snapshot release

- [x] Add `snapshot_json` to the `Version` model and additive migrations.
- [x] Capture the current deal and section draft at submission time.
- [x] Render a frozen version as PDF, with historical fallback for old versions.
- [x] Add submitted-version download handling to both frontends.
- [ ] Add focused tests proving that edits after submission do not alter a downloaded snapshot.
- [ ] Add tests for legacy pre-snapshot reconstruction and invalid snapshot handling.

Acceptance criteria: a submitted PDF is byte/content-stable with respect to later deal edits, both frontends can download it, and access remains deal-scoped.

### Priority 1 - consolidate document ingestion

- [ ] Decide and document the supported public contract for `library`, `documents`, and legacy `uploads` routes.
- [ ] Migrate any required `DealDocument`/`Upload` records to Mistral library metadata.
- [ ] Update remaining UI labels and comments that describe deal documents as "new" or the library as a temporary path.
- [ ] Deprecate compatibility endpoints in OpenAPI before removal.
- [x] Removed unused vector-store configuration and dependency after confirming no code path relies on it.

Acceptance criteria: one primary upload model is used by both frontends and generation, with a tested migration/rollback path for older records.

### Priority 1 - security hardening

- [ ] Disable or restrict self-service role selection during registration for production deployments.
- [ ] Replace unauthenticated-style password reset semantics with a verified reset-token/admin flow.
- [ ] Add login/reset throttling and session revocation controls.
- [ ] Require HTTPS, secure cookies, explicit production CORS origins, and managed secrets outside local development.
- [ ] Decide whether moderation failures should fail closed in regulated environments.
- [ ] Add SSRF controls and an allow/deny policy for section URL scraping.

Acceptance criteria: the production threat model is documented and automated authorization tests cover every deal-scoped route and role transition.

### Priority 2 - persistence and multi-process readiness

- [ ] Replace in-memory Draft All and Manufacture job registries with durable job storage/queueing.
- [ ] Replace process-local agent-library locking with a design safe across multiple API workers, or create deal-scoped agents/tools that need no rebinding.
- [ ] Move local uploads/templates to durable object storage for production.
- [ ] Adopt versioned migrations (Alembic) after importing the existing additive migration state.
- [ ] Define retention/cleanup policies for sessions, audit/version data, local files, and Mistral resources.

Acceptance criteria: jobs survive restarts, multiple workers cannot cross-bind libraries, and schema/storage changes are reversible.

### Priority 2 - evaluation quality

- [ ] Build a regression corpus across all 16 sections, including the PQRS ratio-analysis fixture.
- [ ] Measure citation correctness and source coverage against labeled expectations, not only narrative self-evaluation.
- [ ] Calibrate the saved confidence judge and alert when fallback scoring is used.
- [ ] Record evaluator prompt/model versions with every result.
- [ ] Add failure-budget dashboards for MCP, generation, moderation, judges, and URL scraping.

Acceptance criteria: releases have repeatable quality scores and regressions can be traced to model, prompt, source, or pipeline changes.

### Priority 3 - frontend quality

- [ ] Generate the client from OpenAPI to prevent API contract drift.
- [ ] Add end-to-end tests for login, deal generation, source inspection, review, snapshot download, and export.

Acceptance criteria: the frontend has a single tested API contract.

## Verification matrix

| Area | Automated verification | Manual verification |
|---|---|---|
| Auth/roles | Login, expiry, owner filtering, route-level 403/404 behavior | Exercise RM and analyst workflows |
| MCP | Tool smoke tests, cache/circuit-breaker tests, owner isolation | Browse/select a manufactured company |
| Libraries | Upload/delete/sync tests; library scoping concurrency test | Confirm company and deal sources appear separately |
| Generation | Single and batch service tests with mocked Mistral/MCP | Generate representative mandatory and optional sections |
| Moderation | Safe, flagged, and API-failure tests | Inspect category presentation in UI |
| Evidence | Citation normalization and retrieved-source tests | Open source panels and validate cited pages/files |
| Versions | Narrative final/delete tests; frozen snapshot download tests | Submit, edit afterward, then download old version |
| Exports | Parse/smoke-test PDF, DOCX, and PPTX outputs | Check tables, markdown, theme, and filenames |
| Observability | Metrics serialization and trace setup tests | Inspect `/observability`, Mistral, and Phoenix traces |
| Frontend | `npm run build`, lint, targeted component/E2E tests | Exercise the application on port 8080 |

Suggested local commands:

```powershell
cd backend
pytest

cd ..\frontend
npm run build
npm run lint

```

Tests requiring Mistral, PostgreSQL, MCP, or Phoenix should clearly distinguish unit/mocked runs from live integration runs and must not rely on committed secrets.

## Documentation maintenance rule

Update this file, [README.md](README.md), and [architecture.md](architecture.md) in the same change whenever any of these contracts changes:

- roles or status transitions;
- generation stages, source precedence, or agent count;
- database/library ownership;
- public API paths;
- supported frontend variants or ports;
- version snapshot/export semantics;
- required environment variables or external services.
