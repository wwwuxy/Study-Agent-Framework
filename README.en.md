<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="StudyAgent: your model, your materials, your progress" width="100%" />
</p>

<h1 align="center">StudyAgent Framework</h1>

<p align="center">
  Bring your own model API and keep learning through diagnostics, lessons, practice and reviews.<br />
  <strong>Save your progress. Understand why the next step is recommended.</strong>
</p>

<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>

<p align="center">
  <img src="docs/assets/readme-stack.svg" alt="Python 3.12+ · FastAPI · React 19 · CLI + Web · BYOK · BKT + FSRS" width="780" />
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#preview">Animated tutorials</a> ·
  <a href="#features">Features</a> ·
  <a href="#cli">CLI</a> ·
  <a href="#documentation">Documentation</a>
</p>

## From a learning goal to the next step

StudyAgent is a personal learning workspace. Connect a model, create separate spaces for your goals, and update knowledge estimates and review schedules from actual answers. Web and CLI share the backend and learning history, so you can continue after refreshing the page or closing the terminal.

- **Start without a textbook:** generate a course structure, diagnose your starting point, then study explanations, examples and exercises.
- **Bring your own material:** upload PDF textbooks for chapter retrieval and citations, or teacher-graded papers to identify weak concepts.
- **Adjust the plan through chat:** change your daily time budget, priorities and teaching preferences, then inspect what actually changed.
- **Keep a connected record:** daily tasks, due reviews, rolling statistics, weekly summaries and a learning timeline follow the same goal.

<a id="preview"></a>

## Animated tutorials

These looping GIFs use **actual interaction keyframes from the current Web UI**, with Chinese and English captions. They use an isolated account and fixed offline fixtures: no real textbooks or paid model calls. Waiting periods are shortened; they do not demonstrate real-provider latency or content quality. The Web UI is currently primarily Chinese.

### 1. Read, answer, and continue to the next lesson

Open **专属课堂 (Classroom)** → start or resume → read the explanation and example → submit an answer → review feedback → continue learning.

![Classroom tutorial: prepare a lesson, read, submit an answer, inspect feedback, and continue](docs/assets/readme-learning.gif)

Once every exercise has been submitted, **下一次学习 (Next learning session)** confirms the explanation as read and prepares a lesson from your latest state. Unanswered exercises produce guidance beside the button. Lesson preparation, answer submission and hint requests show loading feedback where the action was triggered.

### 2. Adjust your learning plan through chat

Open **学习对话 (Learning chat)** and ask to study for 15 minutes daily, prioritize process scheduling and use interview-style examples. Inspect the change card and current plan.

![Planning chat tutorial: send a request, clear the composer, and inspect updated time and stages](docs/assets/readme-planning-chat.gif)

Clear requests apply automatically after validation; ambiguous requests trigger clarification. Sending clears the composer immediately; failed requests restore the draft for editing or retry. Previous answers, review history and paused lessons remain available. Replies are published after validation, rather than streamed token by token.

<details>
<summary>View the current knowledge map</summary>

![Current knowledge map with prerequisites, concept details, and learning evidence](docs/assets/readme-knowledge.jpg)

Drag, zoom, fit the canvas, or locate a concept using the selector. Solid lines show main branches; dashed lines preserve other prerequisite relationships. Select a node to inspect objectives, prerequisite knowledge and evidence.

</details>

<a id="quick-start"></a>

## Quick start

### 1. Install and start

Prepare **Python 3.12+, uv, Node.js 22.12+ and npm**. These commands target macOS/Linux; Windows users can use WSL.

```bash
git clone https://github.com/wwwuxy/Study-Agent-Framework.git
cd Study-Agent-Framework

# Install backend, CLI and frontend dependencies, create local config,
# migrate the database, and build the Web UI
./scripts/setup.sh

# Keep this terminal running; the backend serves the API and built Web UI
./scripts/serve.sh
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. Initial setup generates an encryption key, preserves an existing `.env`, and leaves demo mode disabled.

### 2. Start learning in the browser

1. Register or sign in.
2. Open **模型与设置 → 模型连接 (Models & Settings → Model connections)**. Choose a preset or custom endpoint, enter the model and API key, save, then test the connection. Chat, image and PDF capabilities are tested separately; retest after editing a connection.
3. Create a study space, choose a tested model and enter your goal.
4. Start from **今日任务 (Today)** or use **专属课堂 (Classroom)** for diagnostics, lessons and practice.
5. Use **学习对话 (Learning chat)** to adjust your time or priorities and **学习概要 (Learning reports)** to inspect progress.

Calls use your own provider configuration and may incur charges. A connection configuration ID is different from the provider's model name: the ID identifies a saved connection; the model name belongs in its settings.

### 3. No API key? Try the offline demo

Stop any running server, then explicitly enable demo providers:

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

After signing in, choose **离线演示 (Offline demo)** when adding a model, save and test it, then create a space. The demo uses fixed operating-system fixtures. Real-provider failures never silently fall back to a demo.

<details>
<summary>CLI-only installation, development mode, and upgrades</summary>

Install just the backend and CLI without Node.js:

```bash
./scripts/setup.sh --backend-only
./scripts/serve.sh
```

For frontend development:

```bash
./scripts/dev.sh
# Web: http://localhost:5173
# API: http://127.0.0.1:8000
```

Choose either `serve.sh` or `dev.sh` to avoid a port 8000 conflict.

To upgrade, stop the old server, update dependencies, migrate and rebuild:

```bash
git pull --ff-only
./scripts/setup.sh
./scripts/serve.sh
```

`serve.sh` applies database migrations but **does not rebuild an existing frontend**. For frontend-only edits, run `npm --prefix frontend run build`. Restart the server after backend code changes.

</details>

<a id="features"></a>

## Features and pages

| Page | What you can do |
|---|---|
| **Today** | View priority tasks, due reviews and suggestions within your time budget; start, verify completion, skip or postpone |
| **Learning chat** | Adjust goals, time, deadlines, priorities and teaching preferences; inspect changes, history and paused lessons |
| **Classroom** | Diagnose, read explanations and examples, request hints, practice with feedback, and resume unfinished lessons |
| **Knowledge map** | Explore concepts, prerequisites, objectives, estimated mastery and supporting evidence |
| **Private materials** | Upload PDFs, process them in the background, retrieve chapters and citations, download originals, reindex or delete |
| **Exam diagnostics** | Upload graded papers; review per-question results, concept performance and suggestions; correct, retry or delete reports |
| **Learning reports** | Inspect the overview, recent 7/30-day statistics, weekly summaries, spaced reviews and learning history |
| **Models & Settings** | Manage model connections and study spaces, switch teaching models, and inspect background tasks and analysis usage |

### Daily plans, reviews and reports

Daily coordination and weekly statistics use saved learning records and **do not call a model**. Authorized material processing and exam recognition do call the chosen model in the background. Request **AI analysis** explicitly when you want an interpretation of a daily plan or saved weekly report.

The default analysis allowance is 10 requests and 100,000 tokens per day, shared across an account's spaces and reset by UTC date. Reserved and actual usage appear under background operations; provider bills determine monetary charges.

**pyBKT 1.4.3** and **py-fsrs 6.3.2 / FSRS-6** track knowledge and memory separately. Answers, assistance and evidence reliability affect estimates. Uploading, reading and self-reported chat claims do not directly increase mastery. Default parameters are not personally calibrated; estimates are learning aids.

<a id="materials"></a>

## Materials and papers: test capabilities before uploading

| Content | Model requirement | Default upload limits |
|---|---|---|
| **Private textbook** | Custom native Files + Responses connection with verified PDF capability | PDF; 20 MiB per file; up to 20 processed chapters |
| **Graded PDF paper** | Verified native PDF connection | 20 MiB per file |
| **Graded paper photos** | Verified OpenAI-compatible or native image capability | JPG/PNG; up to 20 images; 40 MiB per paper |

The page shows the instance's actual supported formats and limits. Chat support does not imply image or PDF support; retest old or edited connections. Textbook ingestion does not support DOCX/EPUB, and an exam cannot mix PDF and photos.

- **Textbooks:** select a PDF → authorize this transfer → upload and index → automatically publish chapters and concepts → inspect citations in lessons or search results. No manual job execution is required.
- **Papers:** select a graded paper → order photos and optionally enter the exam date → authorize and upload → read the history and question-level report. Only clearly graded results reliably mapped to one existing concept update knowledge estimates. Historical papers do not reset review schedules.
- **Retrieval:** keyword search and model reranking are the default. Remote embeddings are optional after configuration and testing. Verify generated summaries, chapters and page references against the original.
- **Deletion:** removing materials deletes local originals and indexes and attempts remote cleanup. Removing a completed diagnostic retracts its imported evidence and recalculates knowledge state. Provider policies govern remote retention.

See the [material guide](docs/m2-materials.md) and [exam diagnostics guide](docs/exam-diagnostics.md), currently in Chinese.

<a id="cli"></a>

## CLI workflow

The CLI and Web sign in separately but share backend accounts and learning progress. Passwords and API keys use hidden prompts by default.

```bash
source .venv/bin/activate
study-agent auth register --username yourname
# Existing account: study-agent auth login --username yourname

study-agent provider add --name 'My learning model' \
  --model 'provider-model-name' \
  --base-url 'https://api.example.com/v1' \
  --accept-data-transfer

# Replace PROVIDER_ID with the saved connection ID returned above
study-agent provider test PROVIDER_ID
study-agent space create --goal 'Learn operating systems systematically' \
  --provider PROVIDER_ID --minutes 30

study-agent diagnose
study-agent learn
```

Replace the example endpoint and model name with values from your provider.

| Task | Command |
|---|---|
| Start or resume a lesson | `study-agent learn` |
| Read or refresh today's plan | `study-agent today` / `study-agent today --refresh` |
| List or start a task | `study-agent task list` / `study-agent task start TASK_ID` |
| Inspect progress, plan and next step | `study-agent progress` / `study-agent plan` / `study-agent next` |
| Due reviews and recent report | `study-agent review list` / `study-agent report --days 7` |
| Current week or saved summaries | `study-agent weekly current` / `study-agent weekly list` |
| Suggestions or in-app messages | `study-agent suggestion list` / `study-agent inbox list` |
| Analysis allowance or background jobs | `study-agent analysis-usage` / `study-agent activity-jobs list` |
| Learning events or model usage | `study-agent events` / `study-agent runs` |
| Switch spaces | `study-agent space list` → `study-agent space use SPACE_ID` |
| JSON output | `study-agent --json report --days 30` |

Interactive practice supports `/hint`, `/skip` and `/quit`. Put global flags such as `--json`, `--server` and `--timeout` before the main command, for example `study-agent --server https://study.example.com auth login --username yourname`. Learning chat and exam diagnostics currently use the Web UI; there are no dedicated CLI subcommands for them.

<details>
<summary>Upload materials and request AI analysis from the CLI</summary>

Create a native file connection and select the relevant space:

```bash
study-agent provider add --name 'My file model' --files \
  --model 'provider-file-model-name' \
  --base-url 'https://api.example.com/v1' --accept-data-transfer
study-agent provider test FILE_PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider FILE_PROVIDER_ID
study-agent space use SPACE_ID

study-agent material upload '/absolute/path/textbook.pdf' \
  --accept-file-transfer --request-id textbook-001
study-agent job wait JOB_ID --seconds 180
study-agent material search 'process scheduling' --mode keyword
study-agent material show MATERIAL_ID
```

Replace IDs with complete values returned by the corresponding commands. File probing uploads a randomly marked test PDF and attempts deletion; it may incur charges. Each upload or reindex requires its own authorization.

```bash
study-agent --json today --refresh
study-agent analyze --source daily_plan --source-id PLAN_ID
study-agent analysis list
study-agent analysis-usage
```

Use the `id` returned by `study-agent --json today --refresh` as `PLAN_ID`. Analysis calls the current space's model and consumes the daily allowance. See the [CLI guide](docs/cli.md) for further commands.

</details>

## Configuration and data

The complete template is [`.env.example`](.env.example). Local installations use SQLite by default; PostgreSQL and optional pgvector storage are also supported.

| Setting | Default / purpose |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | Generated on first setup; encrypts provider API keys |
| `DATABASE_URL` | `sqlite:///./data/study.db` |
| `MATERIAL_STORAGE_DIR` | `data/materials`; private textbooks and exam attachments |
| `MATERIAL_WORKER_ENABLED` | `true`; process material jobs automatically |
| `MATERIAL_MAX_BYTES` / `MATERIAL_MAX_SECTIONS` | `20971520` / `20` |
| `EXAM_WORKER_ENABLED` / `EXAM_CALL_TIMEOUT_SECONDS` | `true` / 120 seconds |
| `ENABLE_FAKE_PROVIDER` | `false`; demo providers require explicit opt-in |
| `PGVECTOR_ENABLED` | `false`; install the extension and run `scripts/pgvector.sql` first |
| `COOKIE_SECURE` | `true` for HTTPS; setup uses `false` for local HTTP |

API keys are encrypted in the backend, with access scoped by account and space. Goals, context, answers and separately authorized files are sent to the provider you choose. Back up the **database, private material directory and matching encryption key** together. Confirm provider charges, retention and real-model quality separately.

## Maintenance and validation

```bash
./scripts/check.sh
# Ruff and format checks, shell syntax, backend tests, frontend tests, and production build
```

For a dedicated PostgreSQL test database:

```bash
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

Engineering tests use isolated databases, explicit demo adapters and protocol substitutes. They do not establish real-model recognition accuracy or educational effectiveness. See the [full manual](docs/usage.zh-CN.md) for deployment steps and the [README media notes](docs/assets/README.md) for tutorial sources and limitations.

<a id="documentation"></a>

## Documentation

The main READMEs are bilingual. Detailed guides below are primarily Chinese; OpenAPI is machine-readable.

| Document | Contents |
|---|---|
| [Full manual](docs/usage.zh-CN.md) | Setup, deployment, configuration, commands and troubleshooting |
| [Learning chat](docs/planning-chat.md) | Plan changes, paused lessons, retries and data boundaries |
| [Daily tasks and weekly reports](docs/m4-active-learning.md) | Tasks, reviews, suggestions, analysis allowance and background operations |
| [Private materials](docs/m2-materials.md) | PDF capabilities, indexing, citations, deletion and vector retrieval |
| [Exam diagnostics](docs/exam-diagnostics.md) | Image/PDF requirements, question-level reports, corrections and evidence retraction |
| [CLI guide](docs/cli.md) | Interactive learning, JSON, sessions and command reference |
| [Knowledge and reviews](docs/m3-adaptive-learning.md) · [Offline evaluation](docs/m3-evaluation.md) | BKT, FSRS, parameters and evaluation |
| [Architecture](docs/architecture.md) · [API](docs/api.md) · [OpenAPI](docs/openapi.json) | Modules, data model and interfaces |
| [Security](docs/security.md) | Data handling, credential protection and deployment guidance |

---

<p align="center"><strong>Start with a goal. Let evidence guide the way.</strong><br /><a href="README.md">阅读中文版 →</a></p>
