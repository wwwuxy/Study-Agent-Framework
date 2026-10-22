<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="StudyAgent：你的模型、你的教材、你的学习进度" width="100%" />
</p>

<h1 align="center">StudyAgent Framework</h1>

<p align="center">
  使用自己的模型 API，从一个学习目标开始，持续完成诊断、学习、练习与复习。<br />
  <strong>记得你的进度，也解释下一步为什么这样安排。</strong>
</p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>

<p align="center">
  <img src="docs/assets/readme-stack.svg" alt="Python 3.12+ · FastAPI · React 19 · CLI + Web · BYOK · BKT + FSRS" width="780" />
</p>

<p align="center">
  <a href="#quick-start">快速开始</a> ·
  <a href="#preview">动图教程</a> ·
  <a href="#features">功能与页面</a> ·
  <a href="#cli">命令行</a> ·
  <a href="#documentation">完整文档</a>
</p>

## 从学习目标到下一步

StudyAgent 是一个个人学习工作台：连接你选择的模型，为不同目标建立独立学习空间；根据实际作答更新知识掌握状态与复习时间。Web 与 CLI 共用后端和学习记录，刷新页面、退出终端后都可以继续。

- **没有教材也能开始**：生成课程知识结构，先诊断，再学习讲解、示例与练习。
- **有自己的资料**：上传 PDF 教材，检索章节与出处；也可上传已批改试卷，分析薄弱知识点。
- **计划可以调整**：通过学习对话修改每日时间、学习重点与讲解偏好，查看实际生效的变化。
- **进度有记录**：今日任务、到期复习、近期统计、自然周报与学习时间线，围绕同一个目标衔接。

<a id="preview"></a>

## 动图教程

以下 GIF 来自**当前 Web 界面的实际操作关键帧**，带中英文步骤说明，循环播放。使用独立演示账号与固定离线样例，不读取真实教材、不调用付费模型；等待过程经过压缩，不代表真实模型的响应速度或内容质量。

### 1. 阅读、答题，再开始下一次学习

进入「专属课堂」→ 开始或继续课堂 → 阅读讲解与示例 → 提交练习 → 查看反馈 → 下一次学习。

![课堂使用教程：准备课堂、阅读讲解、提交答案、查看反馈并进入下一次学习](docs/assets/readme-learning.gif)

练习全部提交后，点击「下一次学习」会确认本次讲解已读，并按最新学习状态准备新课堂；有未提交的练习时，会在按钮附近说明原因。准备课堂、提交答案与获取提示等操作，都在触发位置显示加载反馈。

### 2. 通过对话调整学习安排

在「学习对话」中输入“每天改成15分钟，先学进程调度，例子贴近面试”，发送后查看修改前后的差异与右侧当前计划。

![学习对话教程：发送需求、立即清空输入框、查看每日时间及学习路线的变化](docs/assets/readme-planning-chat.gif)

明确的需求通过校验后自动应用，信息不足时会先澄清。发送后输入框立即清空，失败时恢复原文供修改或重试；既有作答、复习记录和暂存课堂继续保留。当前回复在完成校验后整体展示，不是逐字流式输出。

<details>
<summary>查看当前知识地图界面</summary>

![当前知识地图：学习目标、前置关系、知识点详情和掌握依据](docs/assets/readme-knowledge.jpg)

可拖动、缩放、居中适配，也可通过下拉框定位知识点。实线表示主分支，虚线表示其他前置关联；选中节点可查看学习目标、前置知识与已有证据。

</details>

<a id="quick-start"></a>

## 快速开始

### 1. 安装并启动

准备 **Python 3.12+、uv、Node.js 22.12+ 和 npm**。以下命令适用于 macOS／Linux；Windows 可使用 WSL。

```bash
git clone https://github.com/wwwuxy/Study-Agent-Framework.git
cd Study-Agent-Framework

# 安装后端、CLI 与前端依赖，生成本机配置，迁移数据库并构建网页
./scripts/setup.sh

# 保持此终端运行；后端同时提供 API 和已构建的 Web 页面
./scripts/serve.sh
```

打开 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**。首次安装会生成独立加密密钥；已有 `.env` 不会被覆盖，演示模式默认关闭。

### 2. 在网页中开始学习

1. 注册或登录学习账号。
2. 打开「模型与设置 → 模型连接」，选择内置供应商或自定义接口，填写模型与 API Key，保存后点击「测试连接」。聊天、图片与 PDF 能力分别检测，修改连接后应重新测试。
3. 点击「新建学习空间」，选择已检测的模型，输入学习目标。
4. 从「今日任务」开始，或进入「专属课堂」完成诊断、讲解与练习。
5. 想调整时间或重点时打开「学习对话」；想查看进度时打开「学习概要」。

模型调用使用你自己的服务配置，可能产生费用。连接配置 ID 与服务商的模型名称是两个不同的值：前者用于管理连接和空间，后者填写在模型设置中。

### 3. 没有 API Key？先体验离线演示

停止已有服务，再明确开启演示：

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

注册／登录后，在「添加模型」中选择「离线演示」，保存并测试连接，再创建学习空间。演示仅提供固定操作系统样例；真实服务失败时不会自动切换为演示。

<details>
<summary>仅安装 CLI、开发模式与升级方法</summary>

只使用 CLI 和后端，不需要 Node.js：

```bash
./scripts/setup.sh --backend-only
./scripts/serve.sh
```

前端开发模式：

```bash
./scripts/dev.sh
# 网页：http://localhost:5173
# API：http://127.0.0.1:8000
```

`serve.sh` 与 `dev.sh` 任选一种，避免同时占用 8000 端口。

升级时，先停止旧服务，再更新依赖、迁移数据库并重新构建前端：

```bash
git pull --ff-only
./scripts/setup.sh
./scripts/serve.sh
```

`serve.sh` 会执行数据库迁移，**不会替你重新构建已有前端**。只改前端代码时，也可先运行 `npm --prefix frontend run build`；后端代码更新后需要重启服务。

</details>

<a id="features"></a>

## 功能与页面

| 页面 | 可以做什么 |
|---|---|
| **今日任务** | 按每日可用时间查看优先任务、到期复习和计划建议；开始、核对完成、跳过或改到明天 |
| **学习对话** | 修改目标、时间、截止日期、学习重点与讲解偏好；查看变化、历史消息及暂存课堂 |
| **专属课堂** | 初始诊断、讲解、示例、提示、练习反馈与下一次学习；继续未完成的课堂 |
| **知识地图** | 探索课程知识点、前置关系、学习目标、掌握状态与证据 |
| **私人教材** | 上传 PDF、自动后台处理、检索章节与来源、下载原文、重新索引与删除 |
| **成绩诊断** | 上传已批改试卷，查看逐题结果、知识点表现与巩固建议；核对报告、重试或删除历史诊断 |
| **学习概要** | 学习概览、最近 7／30 天统计、自然周报、间隔复习与学习记录 |
| **模型与设置** | 管理模型连接与学习空间、切换教学模型，查看后台任务和 AI 分析用量 |

### 今日安排、复习与报告

每日任务和周报使用已保存的学习数据整理，**不调用模型**；教材处理和试卷识别则会在用户授权后，由后台调用所选模型。需要解读今日安排或已保存周报时，再手动点击「生成 AI 分析」。

AI 分析默认每日最多 10 次、100,000 Token，同一账号的空间共享额度，按 UTC 日期重置（北京时间每日 08:00）。预留与实际用量可在「模型与设置 → 后台运行」查看；金额以服务商账单为准。

知识掌握与记忆分别由 **pyBKT 1.4.3** 和 **py-fsrs 6.3.2（FSRS-6）** 跟踪。作答结果、提示使用情况和可靠程度影响评估；上传、阅读和聊天自述不会直接增加掌握度。默认参数尚未针对个人校准，估计结果仅供学习参考。

<a id="materials"></a>

## 教材与试卷：先检测能力，再上传

| 内容 | 模型要求 | 默认上传限制 |
|---|---|---|
| **私人教材** | 自定义供应商的原生 Files + Responses 接口，且 PDF 能力检测通过 | PDF，单文件 20 MiB，最多处理 20 个章节 |
| **已批改 PDF 试卷** | 已检测通过的原生 PDF 接口 | 单文件 20 MiB |
| **已批改试卷照片** | 已检测通过的 OpenAI-compatible 图片接口或原生图片接口 | JPG／PNG，最多 20 张，整卷 40 MiB |

实际支持的格式和限制以页面显示为准。聊天能力通过，不代表该模型支持图片或 PDF；旧连接或修改过的连接需要重新检测。教材不支持 DOCX／EPUB，试卷不混传 PDF 和照片。

- **教材流程**：选择 PDF → 授权本次远端处理 → 上传并建立索引 → 自动提取章节与知识点 → 在课堂或检索结果中查看引用。无需手动运行后台任务。
- **试卷流程**：选择已批改试卷 → 调整照片顺序、填写日期 → 授权并上传 → 查看诊断历史与逐题报告。只有清晰批改且能可靠关联到现有单个知识点的结果，才更新知识状态；历史试卷不重置复习时间。
- **检索方式**：默认关键词检索与模型精排；配置并检测远端 Embedding 后可选向量检索。模型给出的章节、摘要与页码仍需结合原文核对。
- **资料清理**：删除教材会清除本地原文与索引，并尝试清理远端文件；删除已完成诊断会撤回其导入证据并重算知识状态。远端保留以服务商政策为准。

详细步骤见[私人教材指南](docs/m2-materials.md)和[成绩诊断指南](docs/exam-diagnostics.md)。

<a id="cli"></a>

## 命令行使用

Web 与 CLI 分别登录，但共用后端账号数据与学习进度。密码和 API Key 默认通过隐藏输入读取，不必写进命令历史。

```bash
source .venv/bin/activate
study-agent auth register --username yourname
# 已有账号：study-agent auth login --username yourname

study-agent provider add --name '我的学习模型' \
  --model '服务商提供的模型名称' \
  --base-url 'https://你的服务商/v1' \
  --accept-data-transfer

# 将 PROVIDER_ID 替换为上一步返回的连接配置 ID
study-agent provider test PROVIDER_ID
study-agent space create --goal '系统学习操作系统' \
  --provider PROVIDER_ID --minutes 30

study-agent diagnose
study-agent learn
```

| 任务 | 命令 |
|---|---|
| 开始／继续课堂 | `study-agent learn` |
| 查看今日安排／立即更新 | `study-agent today` / `study-agent today --refresh` |
| 查看任务／开始指定任务 | `study-agent task list` / `study-agent task start TASK_ID` |
| 查看知识状态、计划与下一步 | `study-agent progress` / `study-agent plan` / `study-agent next` |
| 到期复习与近期报告 | `study-agent review list` / `study-agent report --days 7` |
| 本周即时统计／历史周报 | `study-agent weekly current` / `study-agent weekly list` |
| 计划建议／站内消息 | `study-agent suggestion list` / `study-agent inbox list` |
| AI 分析额度／后台记录 | `study-agent analysis-usage` / `study-agent activity-jobs list` |
| 学习事件／模型调用 | `study-agent events` / `study-agent runs` |
| 切换空间 | `study-agent space list` → `study-agent space use SPACE_ID` |
| 脚本所需 JSON 输出 | `study-agent --json report --days 30` |

交互答题支持 `/hint`、`/skip` 和 `/quit`。全局 `--json`、`--server`、`--timeout` 等选项放在主命令前，例如 `study-agent --server https://study.example.com auth login --username yourname`。学习对话和成绩诊断目前通过 Web 使用，没有专用 CLI 子命令。

<details>
<summary>CLI 上传教材与手动 AI 分析</summary>

先创建原生文件连接并切换到对应空间：

```bash
study-agent provider add --name '我的文件模型' --files \
  --model '服务商提供的文件理解模型名称' \
  --base-url 'https://你的服务商/v1' --accept-data-transfer
study-agent provider test FILE_PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider FILE_PROVIDER_ID
study-agent space use SPACE_ID

study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --request-id textbook-001
study-agent job wait JOB_ID --seconds 180
study-agent material search '进程调度' --mode keyword
study-agent material show MATERIAL_ID
```

各 ID 替换为对应操作返回的完整值。远端文件检测会上传随机标识 PDF 并尝试删除，可能产生费用。每次上传或重新索引都需要单独授权。

```bash
study-agent --json today --refresh
study-agent analyze --source daily_plan --source-id PLAN_ID
study-agent analysis list
study-agent analysis-usage
```

`PLAN_ID` 使用 `study-agent --json today --refresh` 返回的 `id`；AI 分析会调用当前空间的模型并计入每日额度。更多命令见 [CLI 指南](docs/cli.md)。

</details>

## 配置与数据

完整模板见 [`.env.example`](.env.example)。本机默认使用 SQLite；也支持 PostgreSQL 和可选的 pgvector 扩展。

| 配置 | 默认值／用途 |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | 首次安装生成，用于加密模型 API Key |
| `DATABASE_URL` | `sqlite:///./data/study.db` |
| `MATERIAL_STORAGE_DIR` | `data/materials`，保存私有教材与试卷附件 |
| `MATERIAL_WORKER_ENABLED` | `true`，自动处理教材任务 |
| `MATERIAL_MAX_BYTES` / `MATERIAL_MAX_SECTIONS` | `20971520` / `20` |
| `EXAM_WORKER_ENABLED` / `EXAM_CALL_TIMEOUT_SECONDS` | `true` / `120` 秒 |
| `ENABLE_FAKE_PROVIDER` | `false`，仅显式开启时提供离线演示 |
| `PGVECTOR_ENABLED` | `false`，启用前需要安装扩展并运行 `scripts/pgvector.sql` |
| `COOKIE_SECURE` | HTTPS 使用 `true`；setup 生成的本机 HTTP 配置为 `false` |

API Key 在后端加密保存，账号和空间之间的数据隔离。学习目标、上下文、答案及单独授权的文件会发送至你选择的服务商。备份时同时保存**数据库、资料目录与对应加密密钥**；服务商费用、内容保留和真实模型表现需分别确认。

## 维护与验证

```bash
./scripts/check.sh
# Ruff 检查与格式校验、Shell 语法、后端测试、前端测试和生产构建
```

使用专用 PostgreSQL 测试库时：

```bash
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

工程测试使用隔离数据库、明确的演示适配器与协议替身，不等同于真实模型识别准确率或教育效果验证。部署步骤见[完整手册](docs/usage.zh-CN.md)。[演示素材说明](docs/assets/README.md)记录了 README 动图的来源与边界。

<a id="documentation"></a>

## 完整文档

| 文档 | 内容 |
|---|---|
| [中文完整手册](docs/usage.zh-CN.md) | 安装、部署、配置、命令与故障排查 |
| [学习对话](docs/planning-chat.md) | 计划调整、暂存课堂、失败恢复与数据边界 |
| [每日任务与周报](docs/m4-active-learning.md) | 今日安排、复习、建议、AI 分析额度与后台运行 |
| [私人教材](docs/m2-materials.md) | PDF 能力、索引、引用、删除和向量检索 |
| [成绩诊断](docs/exam-diagnostics.md) | 图片／PDF 要求、逐题报告、核对与证据撤回 |
| [CLI 指南](docs/cli.md) | 交互学习、JSON、会话与命令参考 |
| [掌握评估与复习](docs/m3-adaptive-learning.md) · [离线评测](docs/m3-evaluation.md) | BKT、FSRS、参数与评测方法 |
| [架构](docs/architecture.md) · [API](docs/api.md) · [OpenAPI](docs/openapi.json) | 模块、数据模型与接口 |
| [安全与隐私](docs/security.md) | 数据处理方式、凭证保护与部署建议 |

## 许可证

本项目采用 [MIT 许可证](LICENSE)。第三方依赖及其声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

<p align="center"><strong>以目标为起点，以证据为方向。</strong><br /><a href="README.en.md">Read in English →</a></p>
