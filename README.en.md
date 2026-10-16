<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="StudyAgent: your model, your materials, your progress" width="100%" />
</p>

<h1 align="center">StudyAgent Framework</h1>

<p align="center">
  A personal learning agent powered by your own model API.<br />
  <strong>Start with a goal. Learn with evidence. Pick up where you left off.</strong>
</p>

<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong>
</p>

<p align="center">
  <img src="docs/assets/readme-stack.svg" alt="Python 3.12+ · FastAPI · React 19 · CLI + Web · BYOK · M1 + M2" width="780" />
</p>

<p align="center">
  <a href="#preview">Screenshots</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#cli">CLI workflow</a> ·
  <a href="#materials">Your materials</a> ·
  <a href="#documentation">Documentation</a>
</p>

---

## What can StudyAgent do?

Connect your own model, set a learning goal, take a diagnostic, study explanations, and practice with feedback. You can also upload private PDFs so new teaching retrieves your material evidence first and shows document and chapter references.

**The CLI and Web share one backend and learning history.** Use the same account and space to continue after closing your terminal or refreshing the page.

| | Feature | What you get |
|---|---|---|
| 🧠 | **Bring your own model** | Configure a base URL, API key, and model; test chat, JSON, and optional file capabilities |
| 🎯 | **Learn toward a goal** | A candidate knowledge structure, initial diagnostics, explanations, examples, hints, and exercises |
| 📚 | **Private materials and citations** | Remote PDF understanding, chapter retrieval, source references, and authenticated original downloads |
| 🔄 | **Automatic database updates** | Persist uploads immediately; publish concepts, indexes, and plans after processing, then refresh the UI |
| 📈 | **Progress based on evidence** | Estimate knowledge state from actual answers, record assistance, and explain the next recommendation |
| 💻 | **CLI and Web together** | Interactive practice, JSON output, persistent sessions, progress recovery, and separate learning spaces |

> **Current status:** M1 learning-loop and M2 private-material functionality is implemented. Real BYOK textbook samples, native pgvector, and Docker deployment still need validation in the target environment. M3 and M4 are not implemented. [Validation record, in Chinese](docs/acceptance.md)

<a id="preview"></a>

## Screenshots

### Material retrieval: trace content back to its source

Results include the source document and chapter, with an original download for verification. Unverified page numbers are never presented as reliable references.

![Private-material keyword retrieval with chapter summaries and source citations](docs/assets/m2-library.png)

### Knowledge map: updated automatically after upload

When processing completes, new concepts appear in the database and knowledge map. **They remain undiagnosed: uploading or reading does not directly increase mastery.**

![A newly uploaded concept appears in the knowledge map and remains undiagnosed](docs/assets/auto-upload-database.png)

<sub>These are actual local UI screenshots from isolated demo accounts using explicitly labeled fixed fixtures. They do not prove that a real provider has understood a textbook. The Web UI is currently primarily Chinese; this English README does not imply an English UI translation.</sub>

## The learning loop

![Learning workflow: goal, diagnostic, lesson, practice, evidence, and the next step](docs/assets/learning-loop.en.svg)

- **Without materials:** your model generates candidate curricula and teaching content, marked as unverified.
- **With materials:** retrieve your evidence first. By default, insufficient evidence blocks new teaching; general-knowledge supplementation requires a separate opt-in.
- **With practice:** save answers as learning evidence, then update state and plans through rules. Reading receipts and mastery evidence are handled separately.

<a id="quick-start"></a>

## Quick start

### 1. Install and start

You need **Python 3.12+ and uv**. The Web setup also needs **Node.js 22+ and npm**. The commands below target macOS/Linux; Windows users can use WSL.

```bash
git clone https://github.com/wwwuxy/Study-Agent-Framework.git
cd Study-Agent-Framework

# Install backend, CLI, and Web dependencies; create local config and migrate the database
./scripts/setup.sh

# Keep this terminal running; the backend also serves the built Web UI
./scripts/serve.sh
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**: register or sign in → add and test a model → create a space → start diagnostics and learning.

Setup preserves an existing `.env` and leaves demo mode off. After an upgrade, restarting `serve.sh` runs pending database migrations.

<details>
<summary><strong>CLI-only installation or Web development</strong></summary>

Install only the CLI and backend, without Node.js:

```bash
./scripts/setup.sh --backend-only
./scripts/serve.sh
```

For Web development, start the backend and Vite together:

```bash
./scripts/dev.sh
# Web:     http://localhost:5173
# Backend: http://127.0.0.1:8000
```

Choose either `serve.sh` or `dev.sh`; running both can cause a port 8000 conflict.

</details>

<a id="cli"></a>

### 2. Start learning from your terminal

Open another terminal in the project directory. Passwords and API keys use hidden prompts, so they do not need to appear in shell history.

```bash
source .venv/bin/activate
study-agent auth register --username yourname
# Existing account: study-agent auth login --username yourname

study-agent provider add --name 'My learning model' \
  --model 'provider-chat-model-id' \
  --base-url 'https://api.example.com/v1' \
  --accept-data-transfer
```

Replace the example endpoint and model with your provider's actual values. Replace `PROVIDER_ID` below with the full ID returned by `provider add`:

```bash
study-agent provider test PROVIDER_ID
study-agent space create --goal 'Learn operating systems systematically' \
  --provider PROVIDER_ID --minutes 30

study-agent diagnose
study-agent learn
study-agent progress
study-agent next
```

`--accept-data-transfer` authorizes sending learning goals, context, and answers to the selected provider, acknowledging possible charges and its retention policy.

### 3. No paid key yet? Try the demo

Explicitly enable demo providers when starting the backend:

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

In another terminal, after signing in:

```bash
study-agent provider add --name 'Operating systems demo' --demo
study-agent provider test PROVIDER_ID
study-agent space create --goal 'Learn operating systems' --provider PROVIDER_ID
study-agent diagnose
study-agent learn
```

Use the ID returned for this demo configuration. The demo uses fixed operating-system fixtures, makes no paid model requests, and is never silently substituted when a real provider fails.

<a id="materials"></a>

## Bring your own materials

### Verify file support before uploading

Working chat does not imply working file input. Create a native-file configuration using a service and model that actually implement the Files + Responses protocol:

```bash
study-agent provider add --name 'My file model' --files \
  --model 'provider-file-model-id' \
  --base-url 'https://api.example.com/v1' --accept-data-transfer
study-agent provider test FILE_PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider FILE_PROVIDER_ID
study-agent space use SPACE_ID
```

Replace the model and endpoint, then use your actual model-configuration and space IDs. The probe uploads a framework-generated PDF containing a random marker, enables PDF only after reading that marker back, and attempts to delete the probe file. Testing may incur provider charges.

```bash
study-agent material upload '/absolute/path/textbook.pdf' \
  --accept-file-transfer --request-id textbook-001

# Optional status check. Processing starts automatically; job run is not required.
study-agent job wait JOB_ID --seconds 180
study-agent material search 'process scheduling' --mode keyword
study-agent material show MATERIAL_ID
```

| Automatic update stage | What is persisted |
|---|---|
| Upload accepted | File metadata, hash, owning space, and durable job |
| Remote understanding | Remote references, outline, chapter progress, and recovery checkpoints |
| Validated publication | Chapters, summaries, concepts, sources, optional vectors, and the updated learning plan |
| UI synchronization | Refresh material details, knowledge map, and plan; committed data survives restarts |

Defaults are **20 MiB per file** and **20 chapters**, with the background worker enabled. Each upload or reindex needs explicit consent. Failed jobs can be retried; canceled materials can be reindexed.

<details>
<summary><strong>Material management, retrieval options, and capability matrix</strong></summary>

```bash
study-agent material list
study-agent job show JOB_ID
study-agent job retry FAILED_JOB_ID --request-id retry-001
study-agent job cancel JOB_ID
study-agent material reindex MATERIAL_ID --accept-file-transfer
study-agent material download MATERIAL_ID --output '/new/path/textbook.pdf'
study-agent material remove MATERIAL_ID
```

Deletion removes local originals and indexes immediately, then runs remote cleanup separately. Failed cleanup remains visible and retryable. Downloads do not overwrite existing files.

| Provider configuration | Chat / JSON | PDF | Remote embeddings |
|---|---|---|---|
| Default compatible chat | Actually probed | Disabled | Disabled |
| Native `--files` | Actually probed | Enabled after random-file probe succeeds | Optional after model configuration and a successful probe |
| `--demo` | Fixed fixtures | Unsupported | Unsupported |
| `--demo-files` | Fixed fixtures | Fixed material fixtures; does not read uploaded content | Optional demo vectors |

The default is **keyword matching + reranking by your model**, with no embedding model required. For vector retrieval, add `--embedding-model 'embedding-model-id'` to the native configuration, test it, and pass `--embeddings` for that upload or reindex. Search with `--mode embedding`. Native pgvector storage requires additional administrator setup.

Only actually verified PDF input is enabled; DOCX and EPUB are not supported. File retention and charges follow your provider's policy. The framework performs no local document-body extraction, OCR, or embedding-model inference. [Detailed material guide, in Chinese](docs/m2-materials.md)

</details>

## Everyday commands

| Task | Command |
|---|---|
| Resume learning | `study-agent learn` |
| Inspect knowledge state and evidence | `study-agent progress` |
| Read the plan and next action | `study-agent plan` / `study-agent next` |
| Switch learning spaces | `study-agent space list` → `study-agent space use SPACE_ID` |
| Inspect events and model usage | `study-agent events` / `study-agent runs` |
| Get JSON for scripts | `study-agent --json progress` |
| Connect to another backend | `study-agent --server https://study.example.com auth login --username yourname` |

Interactive practice supports `/hint`, `/skip`, and `/quit`. Put global options such as `--json` and `--server` before the main command. The CLI and browser sign in separately while sharing backend learning records. [Full CLI guide, in Chinese](docs/cli.md)

## Configuration and data

See [`.env.example`](.env.example) for the complete template. Detailed deployment, Docker instructions, and troubleshooting are preserved in the [Chinese manual](docs/usage.zh-CN.md).

| Setting | Default / purpose |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | Generated by initial setup; encrypts backend API keys. Keep a separate secure backup. |
| `DATABASE_URL` | `sqlite:///./data/study.db`; PostgreSQL is also supported |
| `MATERIAL_WORKER_ENABLED` | `true`; process uploads and update the database automatically |
| `MATERIAL_MAX_BYTES` / `MATERIAL_MAX_SECTIONS` | `20971520` / `20` |
| `PGVECTOR_ENABLED` | `false`; install the extension and run `scripts/pgvector.sql` before enabling |
| `ENABLE_FAKE_PROVIDER` | `false`; must be enabled explicitly for demo providers |
| `COOKIE_SECURE` | Keep `true` for HTTPS; setup uses `false` for local HTTP development |

- **Originals and indexes are separate:** private local storage holds originals; the database holds metadata, chapters, and learning records. Back up the database, material directory, and corresponding encryption key.
- **Your provider processes your data:** goals, answers, and authorized files are sent to the remote service you choose; calls may incur charges.
- **Access is scoped by user and space:** CLI state stores sessions and space selection. Provider keys are encrypted in the backend.
- **Generated content remains unverified:** curricula, summaries, and model grading are not authoritative validation. The current rule-based estimates have not been psychometrically calibrated.

## Development and validation

```bash
./scripts/check.sh
# Ruff, formatting, shell syntax, Python tests, frontend tests, and production build

# Use a dedicated PostgreSQL test database, never your production database
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

Existing validation covers background ingestion, restart recovery, source isolation, deletion races, saved-plan synchronization, and concurrent answers. Tests use explicit demo adapters and protocol substitutes. See the [validation record, in Chinese](docs/acceptance.md) for the limits of real BYOK, native pgvector, and Docker verification.

## Roadmap

| Stage | Status | Scope |
|---|---|---|
| **M1 · Learning loop** | Implemented | BYOK, goals, diagnostics, lessons, practice, evidence, plans, and CLI |
| **M2 · Private materials** | Code implemented; some deployment validation pending | Native PDFs, automatic ingestion, durable jobs, retrieval, citations, and deletion |
| **M3 · Adaptive learning** | Not implemented | BKT, spaced repetition, learning reports, and quality evaluation |
| **M4 · Proactive support** | Not implemented | Opt-in scheduling, reminders, and budget controls |

<a id="documentation"></a>

## Documentation

The main READMEs are available in Chinese and English. The detailed guides below are currently in Chinese; OpenAPI is machine-readable.

| Document | Contents |
|---|---|
| [Full Chinese manual](docs/usage.zh-CN.md) | Complete setup, command reference, environment variables, deployment, and troubleshooting |
| [CLI guide](docs/cli.md) | Interactive learning, JSON, sessions, and commands |
| [Private-material guide](docs/m2-materials.md) | File capabilities, jobs, retrieval, deletion, and pgvector |
| [Architecture](docs/architecture.md) · [API](docs/api.md) · [OpenAPI](docs/openapi.json) | Modules, data model, and interfaces |
| [Security](docs/security.md) · [Validation](docs/acceptance.md) | Data boundaries, verified behavior, and pending checks |
| [Development specification](StudyAgent_Framework_Development_Spec.md) · [Roadmap](docs/development-roadmap.md) | Requirements, milestones, and planned work |

---

<p align="center"><strong>Start with a goal. Let evidence guide the way.</strong><br /><a href="README.md">阅读中文版 →</a></p>
