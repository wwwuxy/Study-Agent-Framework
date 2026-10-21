<p align="center">
  <img src="docs/assets/readme-hero.svg" alt="StudyAgent：你的模型、你的教材、你的学习进度" width="100%" />
</p>

<h1 align="center">StudyAgent Framework</h1>

<p align="center">
  用户自带模型 API 的个人学习 Agent。<br />
  <strong>从一个学习目标出发，让每一步都有证据，让下一次学习接得上。</strong>
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/readme-stack.svg" alt="Python 3.12+ · FastAPI · React 19 · CLI + Web · BYOK · M1 + M2 + M3 + M4" width="780" />
</p>

<p align="center">
  <a href="#preview">界面预览</a> ·
  <a href="#quick-start">快速开始</a> ·
  <a href="#cli">命令行使用</a> ·
  <a href="#materials">上传教材</a> ·
  <a href="docs/usage.zh-CN.md">完整中文手册</a>
</p>

---

## StudyAgent 能做什么？

你可以用自己的模型配置，创建学习目标、完成诊断、学习讲解、练习答题，再根据实际证据继续下一步。也可以上传私人 PDF，让教学优先检索教材，并显示文件与章节出处。

**CLI 与 Web 共用后端和学习记录。** 使用同一账号与空间时，关掉终端或刷新网页，进度仍然保留。

| | 功能 | 你会得到什么 |
|---|---|---|
| 🧠 | **连接自己的模型** | 配置 Base URL、API Key 和模型；实际检测聊天、JSON 与可选文件能力 |
| 🎯 | **围绕目标学习** | 生成候选知识结构，安排初始诊断、讲解、示例、提示与练习 |
| 📚 | **私人教材与引用** | 远端理解 PDF，检索章节摘要，展示文件、章节与可下载的原文 |
| 🔄 | **上传后自动入库** | 自动保存文件记录；后台完成后更新知识点、索引和计划，页面同步刷新 |
| 📈 | **用证据记录进度** | 根据实际作答估计知识状态，记录辅助程度，解释下一步推荐 |
| 💻 | **终端与网页协作** | 交互答题、JSON 输出、持久会话、进度恢复与独立学习空间 |

> **当前状态**：M1／M2／M3 功能已实现。所有空间统一启用原生 pyBKT 与 py-fsrs，支持到期复习、7／30 天报告与离线校准。真实教育效果、真实 BYOK 教材样例、pgvector 扩展和 Docker 部署仍需在目标环境验收。M4 已增加每日任务、到期复习与计划建议、自然周报、手动 AI 分析及独立登录／注册页面；不同账号数据隔离，后台不自动调用 LLM。[查看验收记录](docs/acceptance.md)

<a id="preview"></a>

## 界面预览

### 模型、空间与后台统一管理

「模型与设置」整合模型连接、学习空间和后台运行；「学习概要」整合近期统计与自然周报，减少侧栏重复入口。

![统一后的模型与设置页面](docs/assets/settings-tabs.jpg)

### 今日任务与自然周报

后台使用已有学习数据整理安排，不调用模型；需要解释时手动点击 AI 分析。不同账号的数据相互隔离。

![M4 每日任务与真实证据完成状态](docs/assets/m4-daily.jpg)

<details>
<summary>查看自然周报与移动端</summary>

![自然周报](docs/assets/m4-weekly.jpg)
<img src="docs/assets/m4-daily-mobile.jpg" alt="390px 手机端每日任务" width="390" />

</details>

[主动学习使用说明与配置](docs/m4-active-learning.md) · [账号注册页面截图](docs/assets/m4-register.jpg)

### 教材检索：从答案回到出处

检索结果保留文件和章节信息，可下载原文核对；未验证的页码不会被包装成可靠引用。

![私人教材的关键词检索、章节摘要与来源引用](docs/assets/m2-library.png)

### 知识脑图：沿着分支探索知识

知识地图现在使用可交互脑图：学习目标连接各知识点，实线展示主分支，虚线保留其他前置关联。点击节点查看学习目标、前置知识与有效证据；支持拖动、缩放、居中适配和下拉定位，手机端可触摸浏览。

上传任务完成后，新知识点会自动进入数据库与脑图。**新增内容保持待诊断，上传和阅读不会直接增加掌握度。**

![知识脑图、前置关系和知识点详情](docs/assets/knowledge-mind-map.jpg)

<sub>截图来自本机真实界面的独立演示账号，使用明确标注的固定样例；不代表真实服务商已理解教材。当前 Web 界面以中文为主，英文 README 不表示界面已完成英文翻译。</sub>

### 学习概要：回顾真实证据

![7／30 天报告与必启双算法状态](docs/assets/m3-report.png)

<sub>隔离演示账号的固定样例；默认参数未针对真实用户校准。</sub>

## 学习流程

![从目标、诊断、教学、练习到证据更新和下一步推荐的学习流程](docs/assets/learning-loop.zh-CN.svg)

- **没有教材**：由用户模型生成候选课程与教学内容，保留待核实标记。
- **上传教材**：先检索用户资料；证据不足时默认停止新教学，通用知识补充需单独授权。
- **形成进度**：作答保存为学习证据，再由 pyBKT 更新知识状态、py-fsrs 更新记忆与计划；阅读记录与掌握证据分别处理。

<a id="quick-start"></a>

## 快速开始

### 1. 安装并启动

准备 **Python 3.12+、uv**；使用 Web 还需要 **Node.js 22+、npm**。以下命令适用于 macOS／Linux，Windows 可使用 WSL。

```bash
git clone https://github.com/wwwuxy/Study-Agent-Framework.git
cd Study-Agent-Framework

# 安装后端、CLI、Web 依赖，生成本机配置并迁移数据库
./scripts/setup.sh

# 保持此终端运行：后端同时托管已构建的 Web 页面
./scripts/serve.sh
```

打开 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**：注册／登录 → 添加并测试模型 → 创建学习空间 → 开始诊断与学习。

安装脚本不会覆盖已有 `.env`，也不会默认开启演示。已有用户升级后重启 `serve.sh` 即会执行数据库迁移。

<details>
<summary><strong>只用 CLI，或进行 Web 开发</strong></summary>

只安装 CLI 与后端，不需要 Node.js：

```bash
./scripts/setup.sh --backend-only
./scripts/serve.sh
```

Web 开发模式（自动启动后端与 Vite）：

```bash
./scripts/dev.sh
# 网页：http://localhost:5173
# 后端：http://127.0.0.1:8000
```

`serve.sh` 与 `dev.sh` 任选一种运行，避免同时占用 8000 端口。

</details>

<a id="cli"></a>

### 2. 在终端开始学习

另开终端，进入项目目录。密码和 API Key 使用隐藏输入，不必放进命令历史。

```bash
source .venv/bin/activate
study-agent auth register --username yourname
# 已有账号：study-agent auth login --username yourname

study-agent provider add --name '我的学习模型' \
  --model '服务商提供的聊天模型ID' \
  --base-url 'https://你的服务商/v1' \
  --accept-data-transfer
```

将返回的完整模型 ID 替换到 `PROVIDER_ID`，然后执行：

```bash
study-agent provider test PROVIDER_ID
study-agent space create --goal '系统学习操作系统' \
  --provider PROVIDER_ID --minutes 30

study-agent diagnose
study-agent learn
study-agent progress
study-agent next
```

模型 ID 与地址须由服务商提供。`--accept-data-transfer` 表示授权将学习目标、上下文与答案发送至该服务商，知悉可能产生的费用与保留政策。

### 3. 暂时没有付费 Key？先体验演示

启动后端时明确开启演示：

```bash
ENABLE_FAKE_PROVIDER=true ./scripts/serve.sh
```

在已登录的另一个终端中：

```bash
study-agent provider add --name '操作系统演示' --demo
study-agent provider test PROVIDER_ID
study-agent space create --goal '学习操作系统' --provider PROVIDER_ID
study-agent diagnose
study-agent learn
```

这里的 `PROVIDER_ID` 使用本次演示配置返回的 ID。演示使用固定操作系统样例，不访问付费模型，也不会在真实服务失败后静默回退为演示。

<a id="materials"></a>

## 把自己的教材带进来

### 先验证文件能力，再上传

聊天可用并不意味着文件可用。新建原生文件配置，使用实际支持 Files + Responses 协议的服务和模型：

```bash
study-agent provider add --name '我的文件模型' --files \
  --model '服务商提供的文件理解模型ID' \
  --base-url 'https://你的服务商/v1' --accept-data-transfer
study-agent provider test FILE_PROVIDER_ID
study-agent space switch-provider SPACE_ID --provider FILE_PROVIDER_ID
study-agent space use SPACE_ID
```

`FILE_PROVIDER_ID` 与 `SPACE_ID` 分别替换为模型配置和学习空间的完整 ID。检测会上传框架生成的随机标识 PDF，实际读回后才开放 PDF，并尝试删除测试文件；检测可能产生费用。

```bash
study-agent material upload '/绝对路径/教材.pdf' \
  --accept-file-transfer --request-id textbook-001

# 可选：查询处理进度。后台已自动开始，不需要 job run。
study-agent job wait JOB_ID --seconds 180
study-agent material search '进程调度' --mode keyword
study-agent material show MATERIAL_ID
```

| 自动更新阶段 | 持久化内容 |
|---|---|
| 上传成功 | 文件元数据、哈希、所属空间和处理任务 |
| 后台理解 | 上传引用、目录、章节进度与可恢复检查点 |
| 校验并发布 | 章节、摘要、知识点、来源、可选向量和更新后的学习计划 |
| 页面同步 | 自动刷新资料详情、知识地图与计划；重启后仍可读取数据库记录 |

默认单文件 **20 MiB**、最多 **20 个章节**，后台 worker 默认启用。每次上传／重新索引均需单独授权；处理失败可以重试，取消后可重新索引。

<details>
<summary><strong>资料管理、检索选项与能力矩阵</strong></summary>

```bash
study-agent material list
study-agent job show JOB_ID
study-agent job retry FAILED_JOB_ID --request-id retry-001
study-agent job cancel JOB_ID
study-agent material reindex MATERIAL_ID --accept-file-transfer
study-agent material download MATERIAL_ID --output '/新的路径/教材.pdf'
study-agent material remove MATERIAL_ID
```

删除立即移除本地原文和索引，另行执行远端清理；清理失败仍会显示提示与可重试任务。下载不会覆盖已有文件。

| 模型配置 | 聊天／JSON | PDF | 远端 Embedding |
|---|---|---|---|
| 默认兼容聊天接口 | 实际检测 | 不开放 | 不开放 |
| `--files` 原生接口 | 实际检测 | 随机文件探测通过后开放 | 配置模型并检测通过后可选 |
| `--demo` | 固定演示 | 不支持 | 不支持 |
| `--demo-files` | 固定演示 | 固定资料样例，未读取上传内容 | 可选演示向量 |

默认使用**关键词 + 用户模型精排**，不需要向量模型。需要向量方式时，在原生配置中增加 `--embedding-model '向量模型ID'`、重新检测，并在本次上传／重索引增加 `--embeddings`。查询时可用 `--mode embedding`；数据库 pgvector 扩展需要管理员额外安装与初始化。

当前只开放实际验证的 PDF，不支持 DOCX／EPUB。远端文件保留时间与费用遵循所选服务商政策；框架不运行本地正文解析、OCR 或本地 Embedding。[完整教材指南](docs/m2-materials.md)

</details>

## 自适应学习：知识掌握与记忆分别跟踪

![BKT、FSRS 与统一学习流程](docs/assets/m3-adaptive.svg)

每个空间都启用 **pyBKT 1.4.3** 和 **py-fsrs 6.3.2（FSRS-6）**。BKT 从可靠作答估计技能状态；FSRS 保存稳定性、难度、回忆预测和精确到期时间。没有逐空间开关或旧规则回退。

```bash
study-agent algorithms
study-agent review list
study-agent review start --concept CONCEPT_ID --request-id review-001
# 非交互提交：使用 start 返回的复习 ID 和题目 ID
study-agent review submit REVIEW_ID --item ITEM_ID --answer 'A' --rating good --request-id answer-001
study-agent report --days 7
study-agent --json report --days 30
```

Web 新增「复习」和「学习概要」，与 CLI 共用同一题目、事件、卡片和计划。独立答对默认 Good，可选 Hard／Easy；答错或使用提示只能 Again，服务端会校验。阅读和低置信评分不制造掌握或回忆证据；新概念显示待诊断，未作答卡片不会被计为逾期。

默认参数尚未针对真实用户校准。离线工具已实际跑通 pyBKT 原生 EM 和 FSRS 官方优化器；合成数据结果仅验证工程流程，不证明学习效果提升。详见[阶段三说明](docs/m3-adaptive-learning.md)与[评测记录](docs/m3-evaluation.md)。

## 学习需求变了？直接和助手聊

Web 左侧选择 **学习对话**，或在概览／课堂点击“调整学习计划”。例如：

> 每天改成 15 分钟，先学进程调度，例子尽量贴近面试。

明确需求会**自动生效**，并展示时间、重点、路线等前后差异；信息不足时会先澄清。可以调整目标、截止日期、讲解偏好，或补充同空间的新知识。阶段路线由当前模型生成，下一步继续结合 BKT／FSRS 与先修条件安排。

![聊天修改学习需求、展示计划变化与暂存课堂](docs/assets/planning-chat.jpg)

聊天、需求版本与学习路线保存到数据库；CLI 的 `plan`、`next`、`learn` 会读取同一更新。改变内容时可暂存旧课堂，之后继续原题；已有作答和记忆记录继续保留。新增知识保持待诊断，聊天自述不会直接变成已掌握。

<sub>截图使用隔离演示账号和固定样例。聊天调用当前 BYOK 模型可能计费；首版在结构校验后完整发布回复与计划。演示不代表通用自然语言理解质量。</sub>

[使用与故障恢复说明](docs/planning-chat.md)

## 上传已批改试卷，诊断薄弱知识

Web 侧栏新增「成绩诊断」：上传已批改 PDF 或多页 JPG／PNG，由当前用户模型识别逐题对错、得分与批注，生成诊断报告，并用可靠证据更新知识状态和下一步。模糊、部分得分及综合题归因不明会单独标记；历史试卷不会重置复习时间。支持历史报告、核对及失败恢复。[使用与模型要求](docs/exam-diagnostics.md)

## 日常命令速查

| 任务 | 命令 |
|---|---|
| 继续上次学习 | `study-agent learn` |
| 查看知识状态与证据 | `study-agent progress` |
| 到期复习与报告 | `study-agent review list` / `study-agent report --days 7` |
| 查询双算法版本 | `study-agent algorithms` |
| 查看计划与下一步 | `study-agent plan` / `study-agent next` |
| 切换学习空间 | `study-agent space list` → `study-agent space use SPACE_ID` |
| 查看学习事件与调用用量 | `study-agent events` / `study-agent runs` |
| 输出 JSON，便于脚本调用 | `study-agent --json progress` |
| 连接其他后端 | `study-agent --server https://study.example.com auth login --username yourname` |

交互答题支持 `/hint`、`/skip`、`/quit`；全局 `--json`、`--server` 等选项放在主命令之前。CLI 与 Web 需要各自登录，但共享后端学习记录。[CLI 详细说明](docs/cli.md)

## 配置与数据

完整模板见 [`.env.example`](.env.example)，更多配置、Docker 部署和故障排查见[中文完整手册](docs/usage.zh-CN.md)。

| 配置 | 默认值／作用 |
|---|---|
| `CREDENTIAL_ENCRYPTION_KEY` | 首次 setup 生成，用于后端加密 API Key；备份时单独妥善保管 |
| `DATABASE_URL` | `sqlite:///./data/study.db`；可切换 PostgreSQL |
| `MATERIAL_WORKER_ENABLED` | `true`，上传后自动处理并更新数据库 |
| `MATERIAL_MAX_BYTES` / `MATERIAL_MAX_SECTIONS` | `20971520` / `20` |
| `PGVECTOR_ENABLED` | `false`；开启前先安装扩展并执行 `scripts/pgvector.sql` |
| `ENABLE_FAKE_PROVIDER` | `false`，显式开启后才能使用演示 |
| `COOKIE_SECURE` | HTTPS 部署保持 `true`；setup 生成的本机 HTTP 配置为 `false` |

- **原文与索引分别保存**：原文在本机私有目录；元数据、章节和学习记录在数据库。备份时同时保存数据库、资料目录与对应加密主密钥。
- **用户模型处理资料**：目标、答案与授权文件会发给用户选择的远端服务，模型调用可能产生费用。
- **权限按用户和空间隔离**：CLI 本地状态只保存会话和空间选择，API Key 在后端加密保存。
- **内容仍需核实**：模型生成的课程、摘要与评分不等于权威核验；当前算法参数没有做真实用户教育测量校准。

## 开发与验证

```bash
./scripts/check.sh
# Ruff、格式、Shell 语法、Python 测试、前端测试与生产构建

# 专用 PostgreSQL 测试数据库；不要使用生产库
TEST_DATABASE_URL='postgresql+psycopg://user:password@localhost/study_agent_test' \
  .venv/bin/pytest backend/tests -q
```

已有验证覆盖自动后台入库、重启恢复、引用隔离、删除竞态、计划同步与并发答题。验收使用显式演示适配器和协议替身；真实 BYOK 内容质量、原生 pgvector 和 Docker 验收范围见[验收记录](docs/acceptance.md)。

## 路线图

| 阶段 | 当前状态 | 范围 |
|---|---|---|
| **M1 · 学习闭环** | 已实现 | BYOK、目标、诊断、教学、练习、证据、计划与 CLI |
| **M2 · 私人教材** | 代码已实现，部分部署验收待完成 | 原生 PDF、自动入库、持久任务、检索、引用与删除 |
| **M3 · 自适应提升** | 已实现，真实教育效果待验证 | 原生 BKT＋FSRS、到期复习、报告、版本化离线评测 |
| **M4 · 主动陪伴** | 已实现，工程验证见验收记录 | 每日任务、到期复习、偏离建议、自然周报、手动分析配额与账号隔离 |

## 文档导航

| 文档 | 内容 |
|---|---|
| [中文完整手册](docs/usage.zh-CN.md) | 完整安装、命令参考、环境变量、部署与常见问题 |
| [M4 主动学习](docs/m4-active-learning.md) | 每日任务、到期复习与计划建议、周报、分析配额和账号隔离 |
| [CLI 指南](docs/cli.md) | 交互学习、JSON、会话管理与命令详解 |
| [私人教材指南](docs/m2-materials.md) | 文件能力、处理任务、检索、删除与 pgvector |
| [架构](docs/architecture.md) · [API](docs/api.md) · [OpenAPI](docs/openapi.json) | 模块、数据模型和接口 |
| [安全与隐私](docs/security.md) · [验收记录](docs/acceptance.md) | 数据边界、已验证内容与待验证事项 |
| [开发规格](StudyAgent_Framework_Development_Spec.md) · [路线图](docs/development-roadmap.md) | 需求、阶段与后续规划 |

---

<p align="center"><strong>以目标为起点，以证据为方向。</strong><br /><a href="README.en.md">Read in English →</a></p>
