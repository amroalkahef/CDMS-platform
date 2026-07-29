# CDMS Platform — Enterprise AI Platform

An AI Platform built to be reusable across multiple business applications (CDMS,
Legislation Portal, Inquiry Management, HR/Finance/Procurement assistants, ...),
not tied to any single one. See [`CDMS platfrom.md.md`](./CDMS%20platfrom.md.md)
for the full PRD this implements.

Core principle: **the AI Platform is independent from the web application.**
The web app never talks to agents or models directly — it goes through the
Backend, which delegates AI work to the AI Platform over HTTP.

## What's implemented (Phases 1–5, including auth/RBAC)

```
web (Next.js, :3000)
  │  REST
  ▼
backend (FastAPI, :8000)          — auth (JWT, editor/reviewer roles),
  │  REST                           workflows, notifications, permission
  ▼                                 checks before calling the AI Platform
ai-platform (FastAPI, :8001)      — orchestrator (LangGraph) + 5 agents +
  │                                  shared tool library + versioning
  ▼
postgres + pgvector (:5432)       — relational + vector store, one instance,
                                     each service owns its own tables
```

### Phase 1+2 — Core Platform & Agents
- **AI Orchestrator** (`ai-platform/app/orchestrator`): a LangGraph state
  graph that wires agents together. `run_draft` chains
  Retrieval → Authoring → Validation. `run_execute` / `run_publish` handle the
  execute/approve/publish half of the lifecycle.
- **Retrieval Agent**: hybrid search — pgvector cosine similarity over a wide
  candidate pool, falling back to SQL keyword search when the corpus is thin.
- **Authoring Agent**: drafts circulars/decisions/summaries from retrieved
  context only, via the configured chat-completions model (any OpenAI-compatible
  provider). Never searches.
- **Validation Agent**: rule-based checks (missing sections, empty draft, no
  grounding context) plus an LLM check for hallucinations/citation issues.
  Never edits — only reports.
- **Execution Agent**: the only agent that writes to the database. Creates
  the Circular/Decision row, snapshots a version, registers a Workflow with
  the Backend; later publishes it once approved.
- **Communication Agent**: notifies approvers when a workflow is created (and
  at each step advancement), and the requester once it's published.
- **Shared Tool Library** (`app/tools/`): `generate_embeddings`,
  `search_documents`/`search_vector_database`/`search_sql`, `rerank`,
  `store_document`, `ocr`, `send_email`, `call_rest_api`, `log_audit`.
- **Audit logging**: every agent call writes an `AuditLog` row (user, agent,
  action, prompt, tokens, duration, tool calls, response), mirrored into
  Prometheus metrics.

### Authentication & Roles
Local email/password auth (JWT, `backend/app/security.py` + `app/auth.py`) —
the "local JWT now, Entra ID later" path. Two roles, enforced server-side on
every write route (not just hidden in the UI):

- **Editor** — writes the first draft (create/edit Circulars & Decisions),
  submits it for review (status → `pending_approval`), and is the only role
  that can **publish** once it's approved.
- **Reviewer** — reviews everything Editors submit, and can **approve** or
  **reject** with an optional comment. Approving does *not* publish — it
  marks the record `approved` and hands it back to the Editor. Rejecting
  returns it to `draft` with the reviewer's comment attached so the Editor
  can revise and resubmit.

Two demo accounts are seeded on startup (`backend/app/seed.py`, idempotent):
`editor@demo.local` / `Editor123!` and `reviewer@demo.local` / `Reviewer123!`.
`POST /api/auth/register` is open (pick `editor` or `reviewer`) for creating
more — in a real deployment this belongs behind admin provisioning or SSO,
not a public endpoint. Tokens are bearer JWTs (`Authorization: Bearer ...`),
24h expiry, stored client-side in `localStorage`; a 401 anywhere clears the
session and bounces to `/login`.

### Phase 3 — Knowledge Layer
- **Upload → OCR → Clean → Chunk → Embed → Vector DB**, fully local, no
  cloud OCR provider required: `.txt` read directly, `.pdf` text extracted
  via `pypdf` with a Tesseract fallback for scanned pages (`pdf2image` +
  `pytesseract`), images OCR'd directly. `POST /documents/upload` (proxied at
  `/api/ai/documents/upload`); the web **Ingest** page supports both file
  upload and pasting raw text.
- **Re-ranking** (`app/tools/rerank.py`): the chat model judges relevance
  over a wide candidate pool pulled from vector search, since no
  cross-encoder model is bundled.
- **Context Builder** (`app/orchestrator/context_builder.py`): deduplicates
  near-identical chunks and enforces a character budget before handing
  context to the Authoring Agent.

### Phase 4 — Workflow Engine
- **Full CRUD** for Circulars/Decisions (`/circulars`, `/decisions` on the AI
  Platform, proxied at `/api/ai/circulars` / `/api/ai/decisions`): list
  (filter by status/department/search), get, create, update, delete — all
  through the Execution Agent, so every write is audited and versioned.
- **Duplicate detection** (`POST /api/ai/similarity-check`, Validation Agent)
  — a real two-stage RAG pipeline, not a bare cosine-similarity cutoff:
  1. **Retrieve**: the in-progress draft is chunked (`app/tools/embeddings.py`,
     same chunker as the Knowledge Layer) and each chunk is embedded and
     searched against `entity_chunks` (chunk-level embeddings synced on
     every Circular/Decision create/update — see `_sync_entity_chunks` in
     the Execution Agent), so a duplicated paragraph surfaces even inside an
     otherwise-different document. This is merged with a `pg_trgm` trigram
     search on title, which catches near-identical titles independently of
     embeddings and keeps the feature working when the LLM provider is unavailable.
  2. **Verify**: the merged candidates are handed to the chat model with the
     draft, asking for an actual `duplicate` / `related` / `different`
     verdict + one-sentence explanation per candidate — not just a score.
     If the LLM call fails (or there's no vector index yet), it falls back
     to a similarity-threshold heuristic with `verdict: "unknown"` rather
     than erroring.

  Runs live, debounced, in the web console's "Similarity Check" panel while
  creating/editing a record, showing the verdict badge, score, and
  explanation.
- **Versioning**: every Circular/Decision write snapshots an immutable
  `DocumentVersion` row (`GET /api/ai/documents/{type}/{id}/versions`,
  visible on the record's detail page).
- **Approval chain**: `WorkflowStep` rows per workflow (default: single
  Reviewer step; the schema supports multiple steps if you want to extend
  it). Reviewer-only, requires the `reviewer` role. Approve → entity status
  `approved` (Editor must still publish); reject → entity status `draft`
  with the reviewer's comment, notifying the Editor.
- **Richer notifications**: `unread` → `read`/`archived` states,
  `PATCH /api/notifications/{id}`, surfaced in the Dashboard.
- **Dashboard analytics** (`GET /api/ai/stats`): totals, pending-drafts count,
  published count, a recent-activity feed derived from the audit log, and
  circulars with a publication date in the next 30 days.

### Phase 5 — Production readiness
- **Metrics**: `/metrics` (Prometheus) on both services via
  prometheus-fastapi-instrumentator, plus custom `ai_agent_calls_total`,
  `ai_agent_duration_ms`, `ai_agent_tokens_total`, `ai_agent_errors_total`
  recorded from `log_audit`.
- **Tracing**: OpenTelemetry instrumentation (FastAPI + httpx + SQLAlchemy)
  is wired but opt-in — it only activates if `OTEL_EXPORTER_OTLP_ENDPOINT`
  is set, so the base stack doesn't need a collector to boot. Bring it up
  with `docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build`
  (OTel Collector → Tempo → Grafana at :3001, admin/admin not required —
  anonymous viewer enabled; Prometheus at :9090). A starter dashboard
  (agent call rate, error rate, p95 duration, token usage) is
  pre-provisioned.
- **Hardened Dockerfiles**: non-root users, `HEALTHCHECK` on all three
  services (visible as `healthy`/`unhealthy` in `docker compose ps`).
- **CI** (`.github/workflows/ci.yml`): pytest for ai-platform/backend against
  a real Postgres service container, `npm run build` for web, and a Docker
  build-validation matrix over all three images.
- **Kubernetes** (`k8s/`): namespace, ConfigMap/Secret (copy
  `secret.yaml.example` → `secret.yaml`, keep it out of git), a dev-only
  Postgres StatefulSet (swap for managed Postgres+pgvector in production),
  Deployments/Services with liveness/readiness probes for all three apps,
  and an Ingress. Renders cleanly via `kubectl kustomize k8s/` — not yet
  applied against a live cluster, so treat it as a validated starting point,
  not a proven-in-production one.

### Web console (`web/`)
A "Management Portal" UI behind a login screen: dark sidebar navigation
(Dashboard, Circulars, Decisions, AI Assistant, Knowledge Base) showing the
signed-in user's name and role, full English/Arabic i18n with a live
language switch and right-to-left layout for Arabic (via `next-intl` and
locale-prefixed routes `/en/...` / `/ar/...`), and dedicated list +
create/edit + detail pages for Circulars and Decisions (search, status/
department filters, table view). Create/edit and the "New" button are
Editor-only; Reviewers see a read-only list and an Approve/Reject + comment
panel on the detail page for anything awaiting their review; Editors see a
Publish button once a record is approved. AI Draft Generator + Similarity
Check panels live on the create/edit form; version history and the approval
chain (with the reviewer's comment) are on the detail page. The AI Assistant
page is a chat UI over the same Retrieval → Authoring pipeline, with
suggested-question starters. Knowledge Base is the document ingestion page
(upload or paste text) that feeds the vector store the Assistant and
drafting tools retrieve from.

## What's intentionally stubbed / deferred

- **Entra ID / SSO** — local JWT auth is in place; swapping in Microsoft
  Entra ID is the documented upgrade path, not yet done.
- **Admin-only user provisioning** — `POST /api/auth/register` is open by
  design for this scaffold; lock it down (or replace with SSO) before real
  deployment.
- **PDF generation** (`generate_pdf()`) — still raises `NotImplementedError`.
- **RabbitMQ** — not used; nothing here is async/queued yet.
- **Database migrations** — schema changes currently require recreating the
  dev Postgres volume (`docker compose down -v`); there's no Alembic yet, so
  this is not safe for a database with real data.
- **Kubernetes manifests are unproven** — rendered and structurally
  validated, but never `kubectl apply`'d against a live cluster.

## Running locally

1. `cp .env.example .env` and set `LLM_API_KEY` (plus `LLM_BASE_URL`/model
   names if not using plain OpenAI — see comments in `.env.example`; without
   a working key, draft/search/ingest calls will fail and everything else
   still works).
2. `docker compose up --build`
3. Web console: http://localhost:3000
   Backend API docs: http://localhost:8000/docs
   AI Platform API docs: http://localhost:8001/docs

Log in at http://localhost:3000 with one of the seeded demo accounts
(`editor@demo.local` / `Editor123!` or `reviewer@demo.local` / `Reviewer123!`)
— or register your own via the login page's "Register" link.

Try the full loop with both roles (two browser windows/profiles, or log out
and back in between steps):
- **As Editor**: go to **Knowledge Base** and upload a file or paste in a
  policy/circular/decision, so Retrieval has something to find. Then
  **Circulars** or **Decisions** → **New** — use the **AI Draft Generator**
  panel to have the Authoring Agent write the content from a prompt, or type
  it yourself. The **Similarity Check** panel runs live to flag likely
  duplicates. Set Status to "Pending Approval" and save to submit it for
  review.
- **As Reviewer**: open the record's detail page, read it, and Approve or
  Reject with an optional comment. Approving marks it `approved` (not yet
  published); rejecting sends it back to `draft` with your comment.
- **As Editor** again: once approved, the record's detail page shows a
  **Publish** button — publishing snapshots a new version and notifies the
  original author (logged, not actually emailed).
- Use **AI Assistant** (either role) to ask questions grounded in whatever's
  been ingested.
- Switch language with the EN/AR toggle at the top of the sidebar — the
  whole console (including layout direction) switches to Arabic/RTL.

### Optional: observability stack

```
docker compose -f docker-compose.yml -f docker-compose.observability.yml up --build
```

Grafana at http://localhost:3001 (dashboard: "AI Platform — Agents &
Requests"), Prometheus at http://localhost:9090.

## Repo layout

```
ai-platform/    # the AI Platform microservice (orchestrator + agents + tools)
backend/        # business backend (workflows, notifications, AI proxy)
web/            # Next.js console — sidebar app, en/ar i18n, RTL support
observability/  # otel-collector / Tempo / Prometheus / Grafana config
k8s/            # Kubernetes manifests (kustomize)
.github/workflows/ci.yml
docker-compose.yml
docker-compose.observability.yml
.env.example    # LLM_API_KEY and model config (ai-platform only)
```

## Next steps toward the full PRD

- Microsoft Entra ID / SSO in place of local JWT; admin-gated user
  provisioning in place of open registration.
- Alembic migrations instead of `create_all` + volume recreation.
- PDF generation, RabbitMQ for async/scheduled notifications.
- Apply the Kubernetes manifests against a real cluster and iterate from
  there (autoscaling, network policies, a real cert-manager/ingress setup).
