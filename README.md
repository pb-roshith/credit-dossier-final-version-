# Credit Dossier

AI-assisted credit pitch-book workflow for relationship managers and credit analysts. The application combines borrower data, deal documents, structured credit tables, approved web sources, and section-specific Mistral agents to draft, review, version, and export a credit dossier.

## What the application supports

- Cookie-based sign-in, registration, password reset/change, and role-based server-side sessions (30 minutes for business roles; 15 minutes for Administrators).
- Three roles: Relationship Managers create and submit their own deals; Credit Analysts review deals; Administrators manage application security policy from a separate dashboard and cannot access deal workflows.
- Sixteen standard credit sections with section-specific prompts and agents.
- Single-section generation, selected-section generation, and background "Draft all" with progress reporting.
- Hybrid grounding from a shared company Mistral Document Library, a deal-specific library, 16 structured PostgreSQL datasets exposed through the local MCP, and up to 10 section URLs.
- Mistral moderation for custom instructions and templates before generation.
- Source-aware narratives with citations, retrieved-source details, claim classification, confidence scoring, and generation metrics.
- Editable narratives, per-section history, final-version selection, and version deletion.
- Deal submission/review with immutable submission snapshots and PDF download of the submitted state.
- PDF, DOCX, and PPTX exports, plus theme extraction from a reference document.
- Access to previously manufactured MCP company data for repeatable demos.
- Mistral telemetry and optional Arize Phoenix/OpenTelemetry tracing, plus an in-app observability view.

## Repository layout

```text
Credit_Dossier/
|-- backend/          FastAPI, SQLAlchemy, Mistral agents, services, and tests
|-- frontend/         Primary React/TanStack application (http://localhost:8080)
|-- mcp/              Local credit-intelligence MCP and data manufacturer
|-- architecture.md   Current system design and runtime flows
|-- implementation_plan.md
`-- run.md            Short local run guide
```

The frontend uses the backend API and a single HTTP-only session cookie.

## Technology

| Layer | Main technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Uvicorn |
| Frontend | React 19, TypeScript, TanStack Router/Start, Vite 8 |
| UI | Tailwind CSS 4, shadcn/ui, Radix UI |
| AI | Mistral Agents, Document Library, moderation, OCR, and Observability judges |
| Data | PostgreSQL for the normal local stack; SQLite remains supported by the backend |
| Integration | Model Context Protocol over local SSE |
| Export | ReportLab/xhtml2pdf, python-docx, python-pptx |
| Telemetry | Mistral telemetry and optional Arize Phoenix/OpenTelemetry |

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL, or Docker for the included MCP PostgreSQL service
- A Mistral API key

The normal local stack uses two separate PostgreSQL databases:

- `credit_dossier_backend` for application data
- `credit_dossier_mcp` for manufactured structured credit data

### 1. Configure and start the local MCP

```powershell
Copy-Item mcp\.env.example mcp\.env
# Edit mcp\.env with PostgreSQL credentials and MISTRAL_API_KEY.

# Optional: start the included PostgreSQL container.
cd mcp
docker compose up -d postgres
pip install -r requirements.txt
python server.py
```

The MCP SSE endpoint is `http://127.0.0.1:8001/sse`. See [mcp/README.md](mcp/README.md) for its tools and manufacturing workflow.

### 2. Configure and start the backend

```powershell
Copy-Item backend\.env.example backend\.env
# Edit backend\.env. At minimum set MISTRAL_API_KEY, DATABASE_URL,
# MCP_SSE_URL, and strong passwords for the initial role accounts.

cd backend
python -m venv venv
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`; OpenAPI documentation is at `http://127.0.0.1:8000/docs`.

Startup creates missing tables, applies safe additive migrations, seeds configured initial users, connects to MCP when available, and initializes the 16 section agents plus the orchestration agent. MCP connection failure is non-fatal; generation can continue with the available Mistral libraries and manually supplied sources.

### 3. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:8080`.

For the four-terminal version of these instructions, see [run.md](run.md).

## Core workflow

1. Sign in as a Relationship Manager and create a deal. Selecting a known MCP company can prefill borrower details.
2. Add deal documents or initialize/upload to the deal's Mistral library. Company-library references and structured data are resolved by owner and company name.
3. Configure section instructions, output templates, and optional public URLs.
4. Generate one or more sections. The pipeline moderates user inputs, selects relevant sources, assembles section-specific context, generates with Library RAG, and evaluates the result.
5. Edit narratives, inspect sources and confidence details, and choose final section versions.
6. Submit a frozen deal version for review. A Credit Analyst approves or denies it with comments.
7. Download a submitted version as PDF or export the current approved dossier as PDF, DOCX, or PPTX.

## Important API groups

Except for health and authentication, API routes require a valid session. Deal-scoped routes also enforce owner/analyst access.

API failures use stable application codes and correlation event IDs documented in
[`error_codes.md`](error_codes.md). The same code and event ID are written to the audit
trail so support teams can correlate a client-visible failure without exposing internals.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Runtime, agent, MCP, orchestration, and telemetry health |
| `POST` | `/api/auth/login` | Start a session |
| `GET` | `/api/auth/me` | Return the signed-in user |
| `GET` | `/api/auth/configuration` | Return the password policy and allowed recovery questions |
| `POST` | `/api/auth/register` | Create a pending account with a selected business role and three recovery questions |
| `POST` | `/api/auth/account-status` | Check whether a user ID is waiting for administrator approval |
| `POST` | `/api/auth/reset-password/questions` | Retrieve an account's recovery questions |
| `POST` | `/api/auth/reset-password` | Verify three answers and reset the password |
| `PUT` | `/api/auth/security-questions` | Replace the signed-in user's recovery questions |
| `GET/PUT` | `/api/admin/password-policy` | Read or update password policy as Administrator |
| `GET` | `/api/admin/user-approvals` | List accounts waiting for administrator approval |
| `POST` | `/api/admin/user-approvals/{user_id}/approve` | Approve a pending account so it can sign in |
| `GET` | `/api/admin/audit-logs` | Review the complete administrative-action, user-event, and system-error audit trail as Administrator |
| `GET` | `/api/admin/administrative-audit-logs` | Review the separate administrative-action audit trail as Administrator |
| `GET/POST` | `/api/deals` | List visible deals / create an RM-owned deal |
| `GET/PATCH/DELETE` | `/api/deals/{deal_id}` | Read, update, or delete a deal |
| `POST` | `/api/deals/{deal_id}/sections/{section_id}/generate` | Generate one narrative |
| `POST` | `/api/deals/{deal_id}/sections/generate-all/start` | Start background generation |
| `GET` | `/api/deals/{deal_id}/sections/generate-all/jobs/{job_id}` | Read generation progress |
| `GET/POST` | `/api/deals/{deal_id}/library` | List or add deal-library sources |
| `POST` | `/api/deals/{deal_id}/versions` | Submit an immutable review snapshot |
| `PATCH` | `/api/deals/{deal_id}/versions/{version_id}/approve` | Approve as Credit Analyst |
| `PATCH` | `/api/deals/{deal_id}/versions/{version_id}/deny` | Deny with review comments |
| `GET` | `/api/deals/{deal_id}/versions/{version_id}/download` | Download the frozen snapshot as PDF |
| `POST` | `/api/deals/{deal_id}/export/{format}` | Export current content as `pdf`, `docx`, or `pptx` |
| `GET` | `/api/companies` | List MCP companies visible to the user |

Legacy deal-document and section-upload endpoints remain for compatibility, but the Mistral library is the primary generation source.

Direct document uploads are backend-allowlisted to PDF, DOC/DOCX, XLS/XLSX,
PPTX, CSV, TXT, Markdown, and JSON. Template uploads accept DOC/DOCX, TXT, and
Markdown; theme references accept PDF and TXT. The API validates both the extension
and the file signature/content and sanitizes the filename before processing it.

## Configuration

The committed examples are [backend/.env.example](backend/.env.example) and [mcp/.env.example](mcp/.env.example).

| Variable | Purpose |
|---|---|
| `MISTRAL_API_KEY` | Required for agents, OCR, moderation, and libraries |
| `MISTRAL_ACCURACY_JUDGE_ID` | Optional saved Observability judge used for confidence |
| `MISTRAL_ACCURACY_JUDGE_MAX_SCORE` | Maximum raw judge score; normalized to 0-100 |
| `DATABASE_URL` | Backend SQLAlchemy database URL |
| `MCP_SSE_URL` | Local MCP endpoint, normally `http://127.0.0.1:8001/sse` |
| `INITIAL_RELATIONSHIP_MANAGER_*` | Optional initial RM credentials |
| `INITIAL_CREDIT_ANALYST_*` | Optional initial analyst credentials |
| `INITIAL_ADMIN_*` | Optional initial Administrator credentials |
| `SESSION_TIMEOUT_*_MINUTES` | Absolute role-based session limits; business roles max 30, Administrator max 15 |
| `ORCHESTRATION_ENABLED` | Enables orchestration pre-flight; defaults to true |
| `MAX_GROUNDING_CHARS` | Limits assembled grounding context |
| `GENERATION_SEMAPHORE` | Concurrent narrative generation limit |
| `ORCHESTRATION_SEMAPHORE` | Concurrent orchestration limit |
| `PHOENIX_API_KEY`, `PHOENIX_COLLECTOR_ENDPOINT` | Optional Phoenix trace export settings |

By default, passwords must be at least 12 characters and contain uppercase, lowercase,
numeric, and special characters; they may not contain the user ID. Never commit `.env` files.

On Windows, local recoverable secrets can be removed from plaintext `.env` files and
stored in `backend/.data/secrets.aesgcm.json` with AES-256-GCM. The versioned AES keys
are protected for the local machine by DPAPI in
`backend/.data/secret-keyring.dpapi`. Migrate backend secrets from the `backend`
directory with:

```powershell
python -m app.local_secrets .env backend MISTRAL_API_KEY DATABASE_URL INITIAL_ADMIN_PASSWORD PHOENIX_API_KEY
python -m app.local_secrets ..\mcp\.env mcp MISTRAL_API_KEY POSTGRES_PASSWORD
```

Every successful Administrator login checks the protected key's age. At 90 days, all
encrypted secrets are authenticated, decrypted, and atomically re-encrypted with a new
AES-256-GCM key version before the old key is retired. Rotation timestamps and versions
are available from `GET /api/admin/encryption-key-status`; completed or failed rotations
are recorded in the administrator audit log. Back up both protected files together.
DPAPI binds the keyring to this Windows host, so copying it to another host does not make
it decryptable. Windows ACLs on `backend/.data` must allow only the application service
identity and authorized administrators to read these files.

The password policy and recovery-question bank are configurable in `backend/.env` using
`PASSWORD_MIN_LENGTH`, `PASSWORD_MAX_LENGTH`, `PASSWORD_MIN_UPPERCASE`,
`PASSWORD_MIN_LOWERCASE`, `PASSWORD_MIN_DIGITS`, `PASSWORD_MIN_SPECIAL`, and
the pipe-separated `SECURITY_QUESTIONS` value. Character counts may be set to `0` to
disable that requirement. The backend publishes these rules to the account screens and
enforces them for registration, password changes, and password resets. New users must
configure three distinct recovery questions; existing users can configure or replace
theirs from Profile after confirming their current password. The question dropdown also
offers `Custom question`, allowing users to write their own recovery-question text.

Bootstrap the first Administrator with `INITIAL_ADMIN_USER_ID` and
`INITIAL_ADMIN_PASSWORD`; public registration intentionally cannot create administrators.
Self-registered Relationship Manager and Credit Analyst accounts enter the Administrator
approval queue and cannot sign in or reset a password until approved from `/admin`.
Environment password-policy values provide the defaults. After an Administrator saves
the policy at `/admin`, the database-backed values take precedence and survive restarts.
The same dashboard shows the complete administrator-only HTTP audit trail without a
fixed row limit. Each row contains an event ID, UTC timestamp, source IP, user ID,
resource ID, category, event type, HTTP status, outcome, and message. User-associated
activity is categorized as `user_event`; authenticated administrator API activity is
maintained separately as `administrative_action`; HTTP 5xx responses, unhandled
exceptions, and Python `ERROR`/`EXCEPTION` records from background/runtime components
are categorized as `system_error` with outcome `error`. Set
`AUDIT_TRUST_X_FORWARDED_FOR=true` only behind a trusted reverse proxy that overwrites
that header; otherwise the direct network peer address is recorded.

## Verification

```powershell
# Backend tests
cd backend
pytest

# Primary frontend
cd ..\frontend
npm run build
npm run lint

# Local MCP smoke test (MCP must be running)
cd ..
$env:MCP_SSE_URL="http://127.0.0.1:8001/sse"
& .\backend\venv\Scripts\python.exe backend\test_mcp.py
```

## Further documentation

- [architecture.md](architecture.md) describes components, data ownership, and generation/review flows.
- [implementation_plan.md](implementation_plan.md) records implemented capabilities, current transition items, and verification priorities.
- [mcp/README.md](mcp/README.md) documents the local credit-intelligence MCP.
- [run.md](run.md) provides concise startup commands.

## License

Private repository. All rights reserved.
